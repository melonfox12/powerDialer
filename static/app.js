const STATUS_STYLES = {
  new: { label: "New", color: "--muted", className: "neutral" },
  call: { label: "Callback", color: "--amber", className: "callback" },
  disqualified: { label: "Not interested", color: "--red", className: "negative" },
  booked: { label: "Booked", color: "--success", className: "positive" },
  interested: { label: "Interested", color: "--success", className: "positive" },
  do_not_call: { label: "Do not call", color: "--red", className: "negative" },
};
const STATUS_LABELS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.label]));
const STATUS_COLOR_VARS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.color]));

const state = {
  leads: [],
  pool: [],
  timezone_groups: [],
  selected_timezone: null,
  metrics: { today: {}, all_time: {}, daily: [] },
  counts: { total: 0, new: 0, calling: 0, booked: 0 },
  in_flight: [],
  pending_outcome: null,
  active_lead: null,
  running: false,
  paused: false,
  agent_ready: false,
  caller_ids: [],
  last_error: "",
  last_event: "Ready",
};

let toastTimer;
let pollBusy = false;
let outcomeSubmitting = false;
let enteringLiveLine = false;
let dashboardTab = "performance";
let performanceMode = "summary";
let observedActiveLeadId = null;
let lastLiveTranscriptKey = "";
let lastCrmTableSignature = null;
let voiceDevice = null;
let voiceCall = null;
let micTestStream = null;
let micTestRecorder = null;
let micTestContext = null;
let micTestFrame = 0;
let micTestChunks = [];
let micPeakLevel = 0;
let micClippingFrames = 0;
let micPlaybackUrl = null;
const selectedLeadIds = new Set();
let selectionAnchorId = null;
const audioInputStorageKey = "prospect-desk-audio-input";
const audioOutputStorageKey = "prospect-desk-audio-output";
let previousStage = "";
let previousSessionConversations = 0;
let goalCelebrated = false;
let connectedAt = null;
let previousMeetings = 0;
let dismissedBreakForSession = null;
let userInteracted = false;
let audioContext = null;
let celebratedSessionId = null;
let sensoryActivityPrimed = false;
const seenSensoryActivity = new Set();

const byId = (id) => document.getElementById(id);

window.addEventListener("error", (event) => {
  console.error("Unhandled error:", event.error || event.message);
  showToast(`Unexpected error: ${event.message}`, true);
});
window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection:", event.reason);
  showToast(`Unexpected error: ${event.reason?.message || event.reason}`, true);
});

let supabaseClient = null;
let accessToken = null;
let googleAuthEnabled = false;

async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (accessToken) headers.Authorization = `Bearer ${accessToken}`;
  const response = await fetch(path, { ...options, headers });
  const type = response.headers.get("content-type") || "";
  const result = type.includes("application/json") ? await response.json() : await response.text();
  if (response.status === 401 && googleAuthEnabled) {
    showLoginGate(result?.error || "Sign in with Google to continue.");
    throw new Error(result?.error || "Sign in with Google to continue.");
  }
  if (!response.ok) throw new Error(result?.error || `Request failed (${response.status})`);
  return result;
}

function processSensoryActivity(activity) {
  const keyFor = (entry) => `${entry.timestamp || ""}:${entry.source || ""}:${entry.message || ""}`;
  if (!sensoryActivityPrimed) {
    activity.forEach((entry) => seenSensoryActivity.add(keyFor(entry)));
    sensoryActivityPrimed = true;
    return;
  }
  for (const entry of activity) {
    const key = keyFor(entry);
    if (seenSensoryActivity.has(key)) continue;
    seenSensoryActivity.add(key);
    const failedCall = /no human answer|voicemail|answer detection timed out|call request failed|call failed|busy signal/i.test(entry.message || "");
    if (failedCall && ["call", "error"].includes(entry.source)) arcadeSensory.reset();
  }
  if (seenSensoryActivity.size > 160) {
    const recent = activity.map(keyFor);
    seenSensoryActivity.clear();
    recent.forEach((key) => seenSensoryActivity.add(key));
  }
}

function localDateTimeParts(date, timezoneName) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezoneName,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

function nextBusinessCallback(lead) {
  const timeZone = timezoneFor(lead.timezone);
  const today = localDateTimeParts(new Date(), timeZone);
  const tomorrow = new Date(Date.UTC(Number(today.year), Number(today.month) - 1, Number(today.day) + 1));
  const local = {
    year: String(tomorrow.getUTCFullYear()),
    month: String(tomorrow.getUTCMonth() + 1).padStart(2, "0"),
    day: String(tomorrow.getUTCDate()).padStart(2, "0"),
  };
  local.hour = "09";
  local.minute = "00";
  return `${local.year}-${local.month}-${local.day}T${local.hour}:${local.minute}`;
}

function timezoneFor(name) {
  const zones = {
    Eastern: "America/New_York", Central: "America/Chicago",
    Mountain: "America/Denver", Pacific: "America/Los_Angeles",
    Alaska: "America/Anchorage", Hawaii: "Pacific/Honolulu",
  };
  return zones[name] || name || Intl.DateTimeFormat().resolvedOptions().timeZone;
}

function localDateTimeToUtc(value, timezoneName) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Choose a valid callback date and time.");
  const desired = Date.UTC(...[Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5])]);
  let candidate = desired;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = localDateTimeParts(new Date(candidate), timezoneName);
    const observed = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute));
    candidate += desired - observed;
  }
  return new Date(candidate).toISOString();
}

function celebrateBooked() {
  const stage = byId("callStage");
  stage.classList.remove("booked-celebration");
  void stage.offsetWidth;
  stage.classList.add("booked-celebration");
  playCue("booked");
}

function playCue(kind) {
  if (!userInteracted || state.settings?.sounds_enabled === false) return;
  const volume = Number(state.settings?.sound_volume ?? 35) / 100 * 0.07;
  if (volume <= 0) return;
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextType) return;
  if (!audioContext) audioContext = new AudioContextType();
  if (audioContext.state === "suspended") audioContext.resume().catch((error) => console.warn("Audio cue could not resume:", error));
  const now = audioContext.currentTime;
  const notes = kind === "booked" ? [880, 1174.66, 1396.91] : [660];
  notes.forEach((frequency, index) => {
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    const start = now + index * (kind === "booked" ? 0.09 : 0);
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(volume, start + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.001, start + (kind === "booked" ? 0.14 : 0.1));
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.15);
  });
}

class ArcadeSensoryController {
  constructor() {
    this.preferencesKey = "prospect-desk-arcade-profile";
    this.defaults = { enabled: true, reels: true, sound: true, volume: 35, shake: true, haptics: true };
    this.preferences = this.loadPreferences();
    this.viewport = byId("arcadeViewport");
    this.reelWindows = [...this.viewport.querySelectorAll(".arcade-reel-window")];
    this.reels = this.reelWindows.map((windowElement) => {
      const rotor = windowElement.querySelector(".arcade-reel-rotor");
      for (const [index, symbol] of ["＄", "◆", "☎", "🔇", "★"].entries()) {
        const item = document.createElement("span");
        item.className = "arcade-reel-symbol";
        item.textContent = symbol;
        item.style.setProperty("--symbol-angle", `${index * 72}deg`);
        rotor.append(item);
      }
      return rotor;
    });
    this.canvas = byId("arcadeParticles");
    this.context = this.canvas.getContext("2d");
    this.particles = [];
    this.particleFrame = 0;
    this.tickTimer = 0;
    this.tickCount = 0;
    this.timeouts = new Set();
    this.phase = "idle";
    this.activeLeadKey = null;
    this.lastMatchKey = null;
    this.pendingSpinKey = null;
    this.valueAnimation = 0;
    this.viewport.hidden = true;
    this.syncControls();
    window.addEventListener("resize", () => this.resizeCanvas());
    this.resizeCanvas();
  }

  loadPreferences() {
    try {
      const saved = JSON.parse(localStorage.getItem(this.preferencesKey) || "{}");
      const volume = Number(saved.volume ?? this.defaults.volume);
      return {
        ...this.defaults,
        ...saved,
        enabled: saved.enabled ?? this.defaults.enabled,
        reels: saved.reels ?? this.defaults.reels,
        sound: saved.sound ?? this.defaults.sound,
        shake: saved.shake ?? this.defaults.shake,
        haptics: saved.haptics ?? this.defaults.haptics,
        volume: Number.isFinite(volume) ? Math.max(0, Math.min(100, volume)) : this.defaults.volume,
      };
    } catch (error) {
      console.warn("Arcade profile could not be loaded:", error);
      return { ...this.defaults };
    }
  }

  syncControls() {
    byId("arcadeEnabledInput").checked = this.preferences.enabled;
    byId("arcadeReelsInput").checked = this.preferences.reels;
    byId("arcadeSoundInput").checked = this.preferences.sound;
    byId("arcadeVolumeInput").value = this.preferences.volume;
    byId("arcadeShakeInput").checked = this.preferences.shake;
    byId("arcadeHapticsInput").checked = this.preferences.haptics;
    setText("arcadeVolumeValue", `${this.preferences.volume}%`);
    this.viewport.classList.toggle("arcade-reels-disabled", !this.preferences.reels);
  }

  updatePreferences(changes) {
    this.preferences = { ...this.preferences, ...changes };
    if (!this.preferences.enabled) this.stop();
    else if (!this.canPlaySound()) this.stopTicking();
    else if (this.phase === "spinning") this.startTicking();
    this.syncControls();
    try {
      localStorage.setItem(this.preferencesKey, JSON.stringify(this.preferences));
    } catch (error) {
      console.error("Arcade profile could not be saved:", error);
      showToast("Arcade profile could not be saved in this browser.", true);
    }
  }

  schedule(callback, delay) {
    const timer = setTimeout(() => {
      this.timeouts.delete(timer);
      callback();
    }, delay);
    this.timeouts.add(timer);
    return timer;
  }

  clearTimers() {
    clearInterval(this.tickTimer);
    this.tickTimer = 0;
    for (const timer of this.timeouts) clearTimeout(timer);
    this.timeouts.clear();
    document.querySelector(".dialer-run-panel").classList.remove("arcade-failure-flash", "arcade-shake");
  }

  stopTicking() {
    clearInterval(this.tickTimer);
    this.tickTimer = 0;
  }

  stop() {
    this.clearTimers();
    this.stopParticles();
    this.valueAnimation += 1;
    this.phase = "idle";
    this.viewport.hidden = true;
    this.viewport.classList.remove("is-resetting", "is-near-miss", "is-match");
    for (const windowElement of this.reelWindows) {
      windowElement.classList.remove("is-spinning", "is-locking", "is-near-miss");
    }
  }

  startSpin(leadKey) {
    if (!this.preferences.enabled) return;
    if (this.phase === "resetting") {
      this.pendingSpinKey = leadKey;
      return;
    }
    if (this.phase === "spinning" && this.activeLeadKey === leadKey) return;
    this.clearTimers();
    this.stopParticles();
    this.activeLeadKey = leadKey;
    this.phase = "spinning";
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-resetting", "is-near-miss", "is-match");
    this.viewport.querySelector("#arcadeValue").hidden = true;
    this.viewport.querySelector("#arcadeValue").textContent = "";
    setText("arcadeStatus", "Evaluating connection");
    this.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-locking", "is-near-miss");
      windowElement.classList.toggle("is-spinning", this.preferences.reels);
      this.reels[index].style.transition = "";
      this.reels[index].style.transform = "";
    });
    this.startTicking();
  }

  startTicking() {
    this.stopTicking();
    if (!this.canPlaySound()) return;
    this.tickCount = 0;
    this.tickTimer = setInterval(() => {
      this.tickCount += 1;
      this.playTick(540 + Math.min(900, this.tickCount * 12));
    }, 50);
  }

  canPlaySound() {
    return userInteracted && this.preferences.enabled && this.preferences.sound &&
      state.settings?.sounds_enabled !== false && this.preferences.volume > 0;
  }

  playTick(frequency) {
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType || !this.canPlaySound()) return;
    if (!audioContext) audioContext = new AudioContextType();
    if (audioContext.state === "suspended") {
      audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "square";
    oscillator.frequency.setValueAtTime(frequency, now);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(this.preferences.volume / 100 * 0.035, now + 0.003);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.022);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.025);
  }

  playRewardChime() {
    if (!this.canPlaySound()) return;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType) return;
    if (!audioContext) audioContext = new AudioContextType();
    if (audioContext.state === "suspended") {
      audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const notes = [523.25, 659.25, 783.99, 1046.5];
    const volume = this.preferences.volume / 100 * 0.07;
    notes.forEach((frequency, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      const start = audioContext.currentTime + index * 0.085;
      oscillator.type = "triangle";
      oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(volume, start + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      oscillator.connect(gain);
      gain.connect(audioContext.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.17);
    });
  }

  playResetTone() {
    if (!this.canPlaySound()) return;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType) return;
    if (!audioContext) audioContext = new AudioContextType();
    if (audioContext.state === "suspended") {
      audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const now = audioContext.currentTime;
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(80, now);
    oscillator.frequency.linearRampToValueAtTime(40, now + 0.3);
    gain.gain.setValueAtTime(this.preferences.volume / 100 * 0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.32);
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.33);
  }

  vibrate(pattern) {
    if (!this.preferences.enabled || !this.preferences.haptics || typeof navigator.vibrate !== "function") return;
    try {
      navigator.vibrate(pattern);
    } catch (error) {
      console.warn("Haptic feedback could not run:", error);
    }
  }

  match(lead) {
    if (!this.preferences.enabled) return;
    const key = lead?.id || this.activeLeadKey || "active-call";
    if (this.lastMatchKey === key) return;
    this.lastMatchKey = key;
    this.activeLeadKey = key;
    this.clearTimers();
    this.stopTicking();
    this.phase = "matched";
    const animationId = ++this.valueAnimation;
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-resetting", "is-near-miss");
    this.viewport.classList.add("is-match");
    setText("arcadeStatus", "Connection established");
    for (const [index, windowElement] of this.reelWindows.entries()) {
      windowElement.classList.remove("is-spinning", "is-near-miss");
      windowElement.classList.add("is-locking");
      this.schedule(() => {
        this.reels[index].style.transform = "rotateX(-72deg)";
      }, index * 150);
    }
    const value = Math.max(0, Math.round(Number(lead?.estimated_value ?? lead?.value ?? 15)) || 0);
    const valueElement = this.viewport.querySelector("#arcadeValue");
    valueElement.hidden = false;
    this.animateValue(value, valueElement, animationId);
    this.burstParticles();
    if (this.preferences.shake && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const panel = document.querySelector(".dialer-run-panel");
      panel.classList.remove("arcade-shake");
      void panel.offsetWidth;
      panel.classList.add("arcade-shake");
      this.schedule(() => panel.classList.remove("arcade-shake"), 420);
    }
    this.playRewardChime();
    this.vibrate([50, 20, 50, 20, 50]);
  }

  animateValue(target, element, animationId) {
    const start = performance.now();
    const duration = 650;
    const draw = (now) => {
      if (this.phase !== "matched" || animationId !== this.valueAnimation) return;
      const progress = Math.max(0, Math.min(1, (now - start) / duration));
      const eased = 1 - (1 - progress) ** 3;
      element.textContent = `+$${(target * eased).toFixed(2)} Est. Value`;
      if (progress < 1) requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  }

  reset() {
    if (!this.preferences.enabled) return;
    if (this.phase === "resetting") return;
    this.valueAnimation += 1;
    this.clearTimers();
    this.stopParticles();
    this.stopTicking();
    this.phase = "resetting";
    this.pendingSpinKey = null;
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-match");
    this.viewport.classList.add("is-near-miss");
    this.viewport.classList.remove("is-resetting");
    this.viewport.querySelector("#arcadeValue").hidden = true;
    setText("arcadeStatus", "Cycle reset · next prospect");
    this.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-spinning", "is-locking", "is-near-miss");
      if (index === 2) windowElement.classList.add("is-near-miss");
      this.reels[index].style.transition = "transform 80ms linear";
      this.reels[index].style.transform = index === 2
        ? "translateY(50%) rotateX(-216deg)"
        : "rotateX(-72deg)";
    });
    this.flashFailure();
    this.playResetTone();
    this.vibrate(250);
    this.schedule(() => {
      this.viewport.classList.add("is-resetting");
      this.schedule(() => {
        this.viewport.classList.remove("is-resetting", "is-near-miss");
        this.phase = "idle";
        if (this.pendingSpinKey) {
          const nextKey = this.pendingSpinKey;
          this.pendingSpinKey = null;
          this.startSpin(nextKey);
        } else {
          this.viewport.hidden = true;
        }
      }, 270);
    }, 150);
  }

  flashFailure() {
    const panel = document.querySelector(".dialer-run-panel");
    panel.classList.add("arcade-failure-flash");
    this.schedule(() => panel.classList.remove("arcade-failure-flash"), 150);
  }

  resizeCanvas() {
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    this.canvas.width = Math.round(window.innerWidth * ratio);
    this.canvas.height = Math.round(window.innerHeight * ratio);
    this.context.setTransform(ratio, 0, 0, ratio, 0, 0);
  }

  burstParticles() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const colors = ["#e1b76d", "#4cc38a", "#dfff78", "#fff1bd"];
    const originX = window.innerWidth / 2;
    const originY = window.innerHeight / 2;
    this.particles = Array.from({ length: 72 }, () => {
      const angle = Math.random() * Math.PI * 2;
      const speed = 1.5 + Math.random() * 5;
      return {
        x: originX, y: originY,
        vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed,
        life: 45 + Math.random() * 35, size: 2 + Math.random() * 3,
        color: colors[Math.floor(Math.random() * colors.length)],
      };
    });
    if (!this.particleFrame) this.particleFrame = requestAnimationFrame(() => this.drawParticles());
  }

  drawParticles() {
    this.particleFrame = 0;
    this.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
    this.particles = this.particles.filter((particle) => particle.life > 0);
    for (const particle of this.particles) {
      particle.x += particle.vx;
      particle.y += particle.vy;
      particle.vy += 0.035;
      particle.life -= 1;
      this.context.globalAlpha = Math.min(1, particle.life / 20);
      this.context.fillStyle = particle.color;
      this.context.fillRect(particle.x, particle.y, particle.size, particle.size);
    }
    this.context.globalAlpha = 1;
    if (this.particles.length) this.particleFrame = requestAnimationFrame(() => this.drawParticles());
  }

  stopParticles() {
    if (this.particleFrame) cancelAnimationFrame(this.particleFrame);
    this.particleFrame = 0;
    this.particles = [];
    this.context.clearRect(0, 0, window.innerWidth, window.innerHeight);
  }
}

const arcadeSensory = new ArcadeSensoryController();

function showSessionSummary(summary, previous) {
  if (!summary) return;
  const minutes = Math.floor((summary.duration_seconds || 0) / 60);
  const seconds = (summary.duration_seconds || 0) % 60;
  setText("sessionSummaryDuration", `Session length · ${minutes}m ${seconds}s`);
  const values = [
    ["Dials", summary.dials],
    ["Connects", summary.connects],
    ["Conversations", summary.conversations],
    ["Meetings booked", summary.meetings_booked],
    ["Best streak", summary.best_streak],
  ];
  byId("sessionSummaryStats").replaceChildren(...values.map(([label, value]) => {
    const item = document.createElement("div");
    const title = document.createElement("span");
    title.textContent = label;
    const count = document.createElement("strong");
    count.textContent = String(value || 0);
    item.append(title, count);
    return item;
  }));
  const comparison = byId("sessionComparison");
  const delta = previous ? (summary.conversations || 0) - (previous.conversations || 0) : 0;
  comparison.hidden = !previous;
  comparison.textContent = previous
    ? `${delta >= 0 ? "+" : ""}${delta} conversations vs. previous session`
    : "";
  byId("sessionSummaryDialog").showModal();
}

function postJson(path, payload = {}) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function setText(id, value) {
  byId(id).textContent = value;
}

function initials(name) {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  return words.length > 1 ? `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase() : (words[0] || "?").slice(0, 2).toUpperCase();
}

function formatPhoneNumber(phone) {
  const digits = String(phone || "").replace(/\D/g, "");
  if (digits.length === 11 && digits.startsWith("1")) {
    return `(${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return phone || "—";
}

function statusDate(lead) {
  if (!lead.scheduled_until) return "";
  const due = new Date(lead.scheduled_until);
  if (Number.isNaN(due.getTime())) return "";
  return due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function transcriptTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderTranscriptEntries(container, entries, emptyMessage, followLatest = false) {
  const previousScrollTop = container.scrollTop;
  const shouldFollowLatest = followLatest &&
    container.scrollHeight - container.scrollTop - container.clientHeight <= 28;
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "transcript-empty";
    empty.textContent = emptyMessage;
    container.replaceChildren(empty);
    if (followLatest) container.scrollTop = shouldFollowLatest ? container.scrollHeight : previousScrollTop;
    return;
  }
  const ordered = [...entries].sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  container.replaceChildren(...ordered.map((entry) => {
    const row = document.createElement("article");
    row.className = `transcript-entry transcript-entry-${String(entry.speaker || "unknown").toLowerCase()}`;
    const meta = document.createElement("div");
    meta.className = "transcript-entry-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = entry.speaker || "Speaker";
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp);
    const text = document.createElement("p");
    text.textContent = entry.text || "";
    meta.append(speaker, timestamp);
    row.append(meta, text);
    return row;
  }));
  if (followLatest) container.scrollTop = shouldFollowLatest ? container.scrollHeight : previousScrollTop;
}

function openTranscript(lead) {
  const entries = lead.transcript || [];
  byId("transcriptDialogTitle").textContent = `${lead.name || lead.business || lead.phone} · Transcript`;
  byId("transcriptDialogMeta").textContent = `${lead.phone || ""} · ${entries.length} utterance${entries.length === 1 ? "" : "s"}`;
  renderTranscriptEntries(byId("transcriptDialogBody"), entries, "No transcript has been captured for this call.");
  byId("downloadTranscriptButton").dataset.leadId = lead.id;
  byId("transcriptDialog").showModal();
}

function downloadTranscript(lead) {
  const entries = lead.transcript || [];
  const content = entries
    .map((entry) => `[${entry.timestamp || "Time unavailable"}] ${entry.speaker || "Speaker"}: ${entry.text || ""}`)
    .join("\r\n");
  const blobUrl = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  const filenameBase = (lead.business || lead.name || lead.phone || "prospect-transcript")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 80) || "prospect-transcript";
  anchor.href = blobUrl;
  anchor.download = `${filenameBase}-transcript.txt`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}

function importedColumns() {
  const columns = [];
  const standard = /^(name|full name|contact|first name|last name|business|company|organization|organisation|phone(?: number| e\.?164)?|mobile|cell|telephone|time\s?zone|tz|call.?status|status)$/i;
  for (const lead of state.leads) {
    for (const key of Object.keys(lead.fields || {})) {
      if (!standard.test(key) && !columns.includes(key)) columns.push(key);
    }
  }
  return columns;
}

function filteredLeads() {
  const query = byId("searchInput").value.trim().toLocaleLowerCase();
  const filter = byId("statusFilter").value;
  return state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (!query) return true;
    const values = [lead.name, lead.business, lead.phone, lead.status, ...Object.values(lead.fields || {})];
    return values.some((value) => String(value || "").toLocaleLowerCase().includes(query));
  });
}

function crmTableSignature() {
  return JSON.stringify([
    state.pending_outcome?.id || null,
    state.leads.map((lead) => [
      lead.id,
      lead.name,
      lead.business,
      lead.phone,
      lead.timezone,
      lead.status,
      lead.scheduled_until,
      lead.fields,
      lead.transcript?.length || 0,
    ]),
  ]);
}

function renderTable() {
  lastCrmTableSignature = crmTableSignature();
  const head = byId("tableHead");
  const body = byId("tableBody");
  const leads = filteredLeads();
  const extras = importedColumns();
  const currentLeadIds = new Set(state.leads.map((lead) => lead.id));
  for (const id of selectedLeadIds) {
    if (!currentLeadIds.has(id)) selectedLeadIds.delete(id);
  }
  if (!currentLeadIds.has(selectionAnchorId)) selectionAnchorId = null;
  head.replaceChildren();
  body.replaceChildren();

  const selectAllCell = document.createElement("th");
  selectAllCell.className = "selection-cell";
  selectAllCell.scope = "col";
  const selectAll = document.createElement("input");
  selectAll.type = "checkbox";
  selectAll.className = "prospect-checkbox";
  selectAll.setAttribute("aria-label", "Select all visible prospects");
  const selectedVisibleCount = leads.filter((lead) => selectedLeadIds.has(lead.id)).length;
  selectAll.checked = leads.length > 0 && selectedVisibleCount === leads.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < leads.length;
  selectAll.addEventListener("change", () => {
    for (const lead of leads) {
      if (selectAll.checked) selectedLeadIds.add(lead.id);
      else selectedLeadIds.delete(lead.id);
    }
    renderTable();
  });
  selectAllCell.append(selectAll);
  head.append(selectAllCell);

  for (const label of ["Prospect", "Company", "Phone Number", "Timezone", ...extras, "Call status", "Call transcript"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }

  for (const lead of leads) {
    const row = document.createElement("tr");
    row.classList.toggle("selected", selectedLeadIds.has(lead.id));
    const selectionCell = document.createElement("td");
    selectionCell.className = "selection-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "prospect-checkbox";
    checkbox.checked = selectedLeadIds.has(lead.id);
    checkbox.setAttribute("aria-label", `Select ${lead.name || lead.phone || "prospect"}`);
    checkbox.addEventListener("click", (event) => {
      const targetIndex = leads.findIndex((item) => item.id === lead.id);
      const anchorIndex = leads.findIndex((item) => item.id === selectionAnchorId);
      if (event.shiftKey && anchorIndex >= 0 && targetIndex >= 0) {
        const start = Math.min(anchorIndex, targetIndex);
        const end = Math.max(anchorIndex, targetIndex);
        for (const item of leads.slice(start, end + 1)) {
          if (checkbox.checked) selectedLeadIds.add(item.id);
          else selectedLeadIds.delete(item.id);
        }
      } else if (checkbox.checked) {
        selectedLeadIds.add(lead.id);
      } else {
        selectedLeadIds.delete(lead.id);
      }
      selectionAnchorId = lead.id;
      renderTable();
    });
    selectionCell.append(checkbox);
    row.append(selectionCell);

    const contact = document.createElement("td");
    const contactWrap = document.createElement("div");
    contactWrap.className = "contact-cell";
    const avatar = document.createElement("span");
    avatar.className = "contact-avatar";
    avatar.textContent = initials(lead.name || lead.business);
    const copy = document.createElement("span");
    copy.className = "contact-copy";
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const subline = document.createElement("span");
    subline.textContent = lead.business || "Prospect";
    copy.append(name, subline);
    contactWrap.append(avatar, copy);
    contact.append(contactWrap);
    row.append(contact);

    for (const value of [lead.business, lead.phone, lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value === lead.phone ? formatPhoneNumber(lead.phone) : value || "—";
      if (value === lead.phone) {
        cell.className = "phone-cell";
        cell.title = lead.phone || "";
      }
      row.append(cell);
    }

    for (const column of extras) {
      const cell = document.createElement("td");
      cell.title = lead.fields?.[column] || "";
      cell.textContent = lead.fields?.[column] || "—";
      row.append(cell);
    }

    const statusCell = document.createElement("td");
    statusCell.className = "status-cell";
    const select = document.createElement("select");
    select.className = `status-select status-${STATUS_STYLES[lead.status]?.className || "neutral"}`;
    select.setAttribute("aria-label", `Call status for ${lead.name || lead.phone}`);
    for (const value of ["new", "call", "booked", "interested", "disqualified", "do_not_call"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "call" && statusDate(lead) ? `Callback (${statusDate(lead)})` : STATUS_LABELS[value];
      option.selected = lead.status === value;
      if (value === "new" && state.pending_outcome?.id === lead.id) option.disabled = true;
      select.append(option);
    }
    select.addEventListener("change", () => changeLeadStatus(lead, select.value, select));
    statusCell.append(select);
    row.append(statusCell);

    const transcriptCell = document.createElement("td");
    const transcriptButton = document.createElement("button");
    const transcriptCount = lead.transcript?.length || 0;
    transcriptButton.type = "button";
    transcriptButton.className = "transcript-view-button";
    transcriptButton.textContent = transcriptCount ? `View · ${transcriptCount}` : "No transcript";
    transcriptButton.disabled = transcriptCount === 0;
    transcriptButton.setAttribute("aria-label", transcriptCount ? `View ${transcriptCount} transcript utterances for ${lead.name || lead.phone}` : `No transcript for ${lead.name || lead.phone}`);
    transcriptButton.addEventListener("click", () => openTranscript(lead));
    transcriptCell.append(transcriptButton);
    row.append(transcriptCell);
    body.append(row);
  }

  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV to add prospects to your workspace."
    : "Change the search or status filter to see more rows.";
  byId("crmTable").hidden = state.leads.length === 0;
  const summary = `${leads.length} of ${state.leads.length} prospect${state.leads.length === 1 ? "" : "s"}`;
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}

async function selectTimezone(timezone) {
  try {
    Object.assign(state, await postJson("/api/timezone", { timezone: timezone || "" }));
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderTimezoneFilters() {
  const groups = state.timezone_groups || [];
  const totalNew = groups.reduce((sum, group) => sum + group.count, 0);
  const selected = state.selected_timezone || "";
  const knownZones = groups.map((group) => group.name);
  const options = [new Option(`All time zones (${totalNew})`, "")];
  if (selected && !knownZones.includes(selected)) options.push(new Option(selected, selected));
  options.push(...groups.map((group) => new Option(`${group.name} (${group.count})`, group.name)));
  for (const select of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")].filter(Boolean)) {
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    select.value = selected;
  }
}

function renderCallerPool() {
  const pool = state.pool || [];
  renderTimezoneFilters();
  setText("poolTabCount", String(pool.length));
  setText("poolTableSummary", `${pool.length} new prospect${pool.length === 1 ? "" : "s"}${state.selected_timezone ? ` · ${state.selected_timezone}` : ""}${state.skipped_outside_hours ? ` · ${state.skipped_outside_hours} skipped: outside calling hours` : ""}${state.skipped_unknown_timezone ? ` · ${state.skipped_unknown_timezone} skipped: timezone unavailable` : ""}`);
  const body = byId("poolTableBody");
  body.replaceChildren(...pool.map((lead) => {
    const row = document.createElement("tr");
    const prospect = document.createElement("td");
    const contact = document.createElement("div");
    contact.className = "contact-copy";
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const detail = document.createElement("span");
    detail.textContent = lead.business || "Prospect";
    contact.append(name, detail);
    prospect.append(contact);
    row.append(prospect);
    for (const value of [lead.business || "—", lead.phone || "—", lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (value === lead.phone) cell.className = "phone-cell";
      row.append(cell);
    }
    const status = document.createElement("td");
    const statusLabel = document.createElement("span");
    statusLabel.className = "pool-new-status";
    statusLabel.textContent = "New";
    status.append(statusLabel);
    row.append(status);
    const transcript = document.createElement("td");
    const button = document.createElement("button");
    const count = lead.transcript?.length || 0;
    button.type = "button";
    button.className = "transcript-view-button";
    button.textContent = count ? `View · ${count}` : "No transcript";
    button.disabled = count === 0;
    button.addEventListener("click", () => openTranscript(lead));
    transcript.append(button);
    row.append(transcript);
    return row;
  }));
  byId("poolTable").hidden = pool.length === 0;
  byId("poolTableEmpty").classList.toggle("visible", pool.length === 0);
}

function drawProspectWaveform(level = 0) {
  const canvas = byId("prospectWaveform");
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(bounds.width * ratio);
  const height = Math.round(bounds.height * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const normalized = Math.max(0, Math.min(1, level));
  const count = 44;
  const gap = 3;
  const barWidth = Math.max(2, (bounds.width - gap * (count - 1)) / count);
  const center = bounds.height / 2;
  context.fillStyle = normalized > 0.82 ? "#e1b76d" : "#4cc38a";
  for (let index = 0; index < count; index += 1) {
    const envelope = 0.18 + 0.82 * Math.abs(Math.sin(index * 0.38 + performance.now() / 120));
    const variation = 0.35 + Math.random() * 0.65;
    const barHeight = Math.max(2, normalized * bounds.height * envelope * variation);
    const x = index * (barWidth + gap);
    context.fillRect(x, center - barHeight / 2, barWidth, barHeight);
  }
  setText("prospectAudioLevel", `${Math.round(normalized * 100)}%`);
}

function renderCallMonitor() {
  const activity = state.activity_log || [];
  const activityList = byId("activityLog");
  setText("activityCount", `${activity.length} event${activity.length === 1 ? "" : "s"}`);
  activityList.replaceChildren(...activity.slice(-16).map((entry) => {
    const row = document.createElement("li");
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp).replace(/:\d{2}$/, "");
    const source = document.createElement("span");
    source.className = `activity-source activity-source-${entry.source || "dialer"}`;
    source.textContent = entry.source || "dialer";
    const message = document.createElement("span");
    message.className = "activity-message";
    message.textContent = entry.message || "";
    row.append(timestamp, source, message);
    return row;
  }));
  activityList.scrollTop = activityList.scrollHeight;

  const liveTranscript = state.live_transcript || {};
  const lead = state.active_lead || state.pending_outcome ||
    state.leads.find((item) => item.id === liveTranscript.lead_id) || null;
  const partials = lead && liveTranscript.lead_id === lead.id ? liveTranscript.partials || [] : [];
  const entries = [...(lead?.transcript || []), ...partials];
  const waitingCall = (state.in_flight || []).find((call) => call.state === "listening");
  const dialingCall = (state.in_flight || []).some((call) => ["creating", "ringing"].includes(call.state));
  const monitorActivity = byId("monitorActivity");
  const status = state.active_lead
    ? "Live"
    : waitingCall ? "Listening"
      : dialingCall ? "Dialing"
        : state.pending_outcome ? "Wrap-up"
          : state.agent_ready ? "Waiting"
            : state.running ? "Connecting" : "Idle";
  const statusState = status.toLowerCase();
  monitorActivity.dataset.state = ["dialing", "listening", "live"].includes(statusState) ? statusState : "idle";
  byId("enterLiveButton").hidden = !waitingCall;
  byId("enterLiveButton").disabled = enteringLiveLine;
  setText("monitorStatus", status);
  setText("transcriptLiveStatus", liveTranscript.lead_id === lead?.id && liveTranscript.transcribing
    ? "Listening"
    : lead?.transcript?.length ? "Saved" : "Waiting");
  const transcriptKey = JSON.stringify([lead?.id || null, entries]);
  if (transcriptKey !== lastLiveTranscriptKey) {
    lastLiveTranscriptKey = transcriptKey;
    renderTranscriptEntries(
      byId("liveTranscript"),
      entries,
      lead ? "Waiting for the first words…" : "Transcript appears here as the prospect and agent speak.",
      true,
    );
  }
}

byId("callMonitorDisclosure").addEventListener("toggle", () => {
  if (byId("callMonitorDisclosure").open) {
    renderCallMonitor();
    byId("liveTranscript").scrollTop = byId("liveTranscript").scrollHeight;
    drawProspectWaveform();
  }
});

function renderDialer() {
  const stage = state.stage || "idle";
  const connected = state.running && state.agent_ready;
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const activeLeadId = active?.id || null;
  if (activeLeadId && activeLeadId !== observedActiveLeadId) byId("callMonitorDisclosure").open = true;
  observedActiveLeadId = activeLeadId;
  const busy = state.running || Boolean(pending);
  const connection = byId("connectionState");
  connection.classList.toggle("busy", busy && !state.last_error);
  connection.classList.toggle("error", Boolean(state.last_error));
  connection.querySelector("span:last-child").textContent = state.last_error
    ? "Needs attention"
    : pending ? "Outcome needed" : state.paused ? "Paused" : connected ? "Dialing" : state.running ? "Connecting" : "Ready";

  const indicator = document.querySelector(".live-indicator");
  indicator.classList.toggle("on", connected && !state.paused);
  setText("liveLabel", pending ? "OUTCOME REQUIRED" : active ? "LIVE CALL" : state.paused ? "DIALER PAUSED" : connected ? "DIALING" : state.running ? "CONNECTING" : "DIALER STANDBY");
  setText("lineCount", `${state.session_stats?.dials || 0} of ${state.queue_count ?? state.pool?.length ?? 0} dialed`);
  const dialerMessage = state.last_error || (pending
    ? "Choose an outcome to continue dialing."
    : state.paused ? "Paused. Existing calls stay connected."
      : connected ? "One new prospect is called at a time."
        : state.running ? "Waiting for computer audio to connect."
          : "");
  byId("dialerMessage").hidden = !dialerMessage;
  setText("dialerMessage", dialerMessage);
  byId("dialerMessage").classList.toggle("error", Boolean(state.last_error));

  const target = active || pending || (state.in_flight?.find((call) => call.state === "connecting")?.lead);
  const ringing = state.in_flight?.some((call) => call.state === "ringing");
  const activeCall = byId("activeCall");
  activeCall.replaceChildren();
  const avatar = document.createElement("div");
  avatar.className = "active-avatar";
  avatar.textContent = target ? initials(target.name || target.business) : "PD";
  const copy = document.createElement("div");
  copy.className = "active-copy";
  const primary = document.createElement("strong");
  const firstUp = state.next_lead;
  primary.textContent = target
    ? (target.name || target.business || target.phone)
    : firstUp ? `${state.pool.length} prospects queued · First up: ${firstUp.business || firstUp.name || formatPhoneNumber(firstUp.phone)}`
      : "No prospects queued";
  const secondary = document.createElement("span");
  secondary.textContent = target
    ? [target.business, target.phone].filter(Boolean).join(" · ")
    : "";
  copy.append(primary, secondary);
  activeCall.append(avatar, copy);

  byId("startButton").disabled = state.running;
  byId("pauseButton").disabled = !state.running;
  byId("pauseButton").textContent = state.paused ? "Resume" : "Pause";
  byId("hangupButton").disabled = !active && !ringing;
  byId("hangupButton").classList.toggle("button-danger-quiet", Boolean(active || ringing));
  byId("hangupButton").classList.toggle("button-secondary", !active && !ringing);
  byId("skipVoicemailButton").disabled = !active && !(state.in_flight?.length);
  byId("stopButton").disabled = !state.running;
  const caller = state.caller_ids?.[0];
  byId("callerIdLine").hidden = !caller;
  byId("callerIdLine").querySelector("span").textContent = caller || "Not connected";
  renderCallMonitor();

  const outcomeLead = pending;
  const outcomeDisabled = !outcomeLead || outcomeSubmitting;
  byId("outcomeRow").hidden = !outcomeLead;
  byId("outcomeCallButton").disabled = outcomeDisabled;
  byId("outcomeBookedButton").disabled = outcomeDisabled;
  byId("outcomeDisqualifiedButton").disabled = outcomeDisabled;
  for (const id of ["outcomeNoAnswerButton", "outcomeDncButton"]) byId(id).disabled = outcomeDisabled;
  const callbackPicker = byId("callbackPicker");
  callbackPicker.hidden = !state.pending_outcome || !callbackPicker.dataset.open;
  const advancing = Boolean(state.advance_at && !state.paused);
  byId("advanceControls").hidden = !advancing;
  byId("autoAdvance").hidden = !advancing;
  byId("advanceNowButton").hidden = !advancing;
  if (advancing) {
    const seconds = Math.max(0, Math.ceil(Number(state.advance_at) - Date.now() / 1000));
    byId("autoAdvance").textContent = `Next prospect dialing in ${seconds}s · Space to skip`;
  }
  if (!state.pending_outcome) callbackPicker.dataset.open = "";
  renderSessionMomentum();
  renderCallStage(stage, target);
}

function renderSessionMomentum() {
  const stats = state.session_stats || {};
  const goal = Number(stats.goal || state.settings?.session_goal || 20);
  const conversations = Number(stats.conversations || 0);
  setText("sessionGoalLabel", `${conversations} / ${goal} conversations`);
  const progress = byId("sessionGoalTrack");
  progress.setAttribute("aria-valuemax", String(goal));
  progress.setAttribute("aria-valuenow", String(Math.min(conversations, goal)));
  byId("sessionGoalProgress").style.width = `${goal ? Math.min(100, conversations / goal * 100) : 0}%`;
  const streak = Number(stats.current_streak || 0);
  const streakElement = byId("sessionStreak");
  streakElement.hidden = streak < 2;
  streakElement.textContent = streak >= 2 ? `${streak} connects in the last 10 min` : "";
  const sessionId = stats.id || "";
  if (sessionId !== celebratedSessionId) {
    celebratedSessionId = sessionId;
    goalCelebrated = localStorage.getItem(`prospect-desk-goal-${sessionId}`) === "shown";
    previousSessionConversations = conversations;
    previousMeetings = Number(stats.meetings_booked || 0);
    dismissedBreakForSession = null;
  }
  if (conversations >= goal && !goalCelebrated) {
    goalCelebrated = true;
    localStorage.setItem(`prospect-desk-goal-${sessionId}`, "shown");
    showToast("Session goal reached — great work!");
  }
  if (Number(stats.meetings_booked || 0) > previousMeetings) byId("statBookedToday").classList.add("meeting-highlight");
  previousMeetings = Number(stats.meetings_booked || 0);
  previousSessionConversations = conversations;
  const nudgeMinutes = Number(state.settings?.break_nudge_minutes || 90);
  const elapsed = (Date.now() - Date.parse(stats.started_at || Date.now())) / 60000;
  const showNudge = state.running && elapsed >= nudgeMinutes && dismissedBreakForSession !== sessionId;
  byId("breakNudge").hidden = !showNudge;
}

function renderCallStage(stage, target) {
  const container = byId("callStage");
  container.hidden = stage === "idle";
  container.dataset.stage = stage;
  const fragment = document.createDocumentFragment();
  const heading = document.createElement("strong");
  const detail = document.createElement("span");
  if (stage === "connected" && target) {
    heading.textContent = "LIVE";
    const started = state.active_call_started_at ? Date.parse(state.active_call_started_at) : Date.now();
    const seconds = Math.max(0, Math.floor((Date.now() - started) / 1000));
    const clock = localTimeLabel(target.timezone);
    detail.textContent = `${target.business || target.name || "Prospect"} · ${formatPhoneNumber(target.phone)} · ${clock || target.timezone} · ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
    const script = document.createElement("span");
    script.className = "call-stage-script";
    script.textContent = `Opener · ${state.settings?.opening_script || "Introduce yourself, confirm you have the right person, then ask one clear question."}`;
    fragment.append(script);
    container.classList.add("call-stage-live");
    if (previousStage !== "connected") playCue("connect");
  } else if (stage === "paused") {
    heading.textContent = "Session paused";
    detail.textContent = "Resume when you’re ready to continue the queue.";
    const resume = document.createElement("button");
    resume.type = "button";
    resume.className = "button button-primary stage-resume";
    resume.textContent = "Resume";
    resume.addEventListener("click", () => byId("pauseButton").click());
    fragment.append(resume);
    container.classList.remove("call-stage-live");
  } else if (stage === "wrapup" && target) {
    heading.textContent = "Call complete";
    detail.textContent = `Choose a disposition for ${target.business || target.name || formatPhoneNumber(target.phone)}.`;
    container.classList.remove("call-stage-live");
  } else if (stage === "dialing" || stage === "ringing") {
    const calls = state.in_flight || [];
    heading.textContent = stage === "ringing" ? "Ring in progress" : "Dialing next prospect";
    detail.textContent = calls.map((call) => `${call.lead?.business || call.lead?.name || "Prospect"} · ${call.state === "ringing" ? "Ringing" : "Dialing"}`).join(" · ") || state.last_event || "Connecting to the next prospect…";
    container.classList.remove("call-stage-live");
  } else if (stage !== "idle") {
    const next = state.next_lead;
    const clock = next ? localTimeLabel(next.timezone) : "";
    const context = next && Object.entries(next.fields || {}).find(([key, value]) => /notes?/i.test(key) && value);
    detail.textContent = next
      ? `Next up: ${next.business || next.name || "Prospect"} · ${formatPhoneNumber(next.phone)} · ${clock || next.timezone || "Local time unavailable"} · ${context ? `Context: ${context[1]}` : `Status: ${STATUS_LABELS[next.status] || "New"}`}${state.skipped_outside_hours ? ` · ${state.skipped_outside_hours} skipped: outside calling hours` : ""}${state.skipped_unknown_timezone ? ` · ${state.skipped_unknown_timezone} skipped: timezone unavailable` : ""}`
      : state.skipped_outside_hours || state.skipped_unknown_timezone
        ? [
          state.skipped_outside_hours && `${state.skipped_outside_hours} skipped: outside calling hours; they’ll be dialed when local hours open.`,
          state.skipped_unknown_timezone && `${state.skipped_unknown_timezone} skipped: timezone unavailable.`,
        ].filter(Boolean).join(" ")
        : "No prospects available in this queue.";
    container.classList.remove("call-stage-live");
  }

  function localTimeLabel(timezoneName) {
    const zones = {
      Eastern: "America/New_York",
      Central: "America/Chicago",
      Mountain: "America/Denver",
      Pacific: "America/Los_Angeles",
      Alaska: "America/Anchorage",
      Hawaii: "Pacific/Honolulu",
    };
    const zone = zones[timezoneName] || timezoneName;
    try {
      const timeText = new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit", timeZone: zone }).format(new Date());
      return `${timeText} ${timezoneName}`;
    } catch (error) {
      if (error instanceof RangeError) return "";
      throw error;
    }
  }
  if (stage !== "idle") fragment.append(heading, detail);
  container.replaceChildren(fragment);
  if (stage !== previousStage && stage !== "idle") {
    setText("stageAnnouncer", stage === "connected" ? "Human prospect connected" : stage === "wrapup" ? "Call ended. Choose a disposition." : stage === "paused" ? "Dialing session paused." : stage === "ringing" ? "Prospect line is ringing." : "Dialing next prospect.");
    container.classList.remove("stage-enter");
    void container.offsetWidth;
    container.classList.add("stage-enter");
  }
  if (stage === "idle" && previousStage !== "idle") setText("stageAnnouncer", "Dialing session stopped.");
  if (stage === "connected" && previousStage !== "connected") connectedAt = Date.now();
  if (stage === "connected" && previousStage !== "connected") arcadeSensory.match(state.active_lead);
  if (previousStage === "connected" && stage === "wrapup") arcadeSensory.reset();
  if (previousStage === "ringing" && stage === "dialing") arcadeSensory.reset();
  if ((stage === "idle" || stage === "paused") && stage !== previousStage) arcadeSensory.stop();
  if (stage === "dialing" || stage === "ringing") {
    const call = (state.in_flight || []).find((item) => ["creating", "ringing"].includes(item.state));
    const lead = call?.lead || state.next_lead;
    arcadeSensory.startSpin(lead?.id || call?.lead_id || "dialing");
  }
  if (stage !== "connected") connectedAt = null;
  previousStage = stage;
}

function formatMinutes(totalSeconds) {
  const minutes = Math.round((totalSeconds || 0) / 60);
  return `${minutes}m`;
}

function dayLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return dateStr.slice(5);
  return date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
}

function buildMetricsLineChart(series) {
  const container = byId("metricsLineChart");
  const hasActivity = series.some((day) => (day.dials || 0) > 0 || (day.connected || 0) > 0);
  const panel = container.closest(".performance-chart-panel");
  panel.classList.toggle("has-no-data", !hasActivity);
  if (!hasActivity) {
    container.textContent = "No call activity in the last 7 days.";
    container.setAttribute("aria-label", "No call activity in the last 7 days");
    return;
  }
  container.setAttribute("aria-label", "Dials and connected calls trend over the last 7 days");
  const width = 620;
  const height = 190;
  const left = 36;
  const right = 10;
  const top = 12;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maxValue = Math.max(1, ...series.map((day) => Math.max(day.dials || 0, day.connected || 0)));
  const xFor = (index) => left + index * plotWidth / Math.max(1, series.length - 1);
  const yFor = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const svgParts = [];

  for (let step = 0; step <= 2; step += 1) {
    const value = Math.round(maxValue * (2 - step) / 2);
    const y = top + plotHeight * step / 2;
    svgParts.push(`<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="line-chart-gridline" />`);
    svgParts.push(`<text x="${left - 8}" y="${y + 3}" class="line-chart-axis-label">${value}</text>`);
  }

  for (const metric of ["dials", "connected"]) {
    const points = series.map((day, index) => `${xFor(index)},${yFor(day[metric] || 0)}`);
    svgParts.push(`<polyline points="${points.join(" ")}" class="line-series line-series-${metric}" />`);
    series.forEach((day, index) => {
      svgParts.push(`<circle cx="${xFor(index)}" cy="${yFor(day[metric] || 0)}" r="3" class="line-point line-point-${metric}"><title>${dayLabel(day.date)}: ${day[metric] || 0} ${metric}</title></circle>`);
    });
  }

  series.forEach((day, index) => {
    svgParts.push(`<text x="${xFor(index)}" y="${height - 7}" class="line-chart-day-label">${dayLabel(day.date)}</text>`);
  });
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="presentation">${svgParts.join("")}</svg>`;
}

function pieSlicePath(cx, cy, radius, startAngle, endAngle) {
  const startRadians = startAngle * Math.PI / 180;
  const endRadians = endAngle * Math.PI / 180;
  const startX = cx + radius * Math.cos(startRadians);
  const startY = cy + radius * Math.sin(startRadians);
  const endX = cx + radius * Math.cos(endRadians);
  const endY = cy + radius * Math.sin(endRadians);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M${cx},${cy} L${startX},${startY} A${radius},${radius} 0 ${largeArc} 1 ${endX},${endY} Z`;
}

function buildStatusPieChart(leads) {
  const chart = byId("statusPieChart");
  const legend = byId("statusPieLegend");
  const statuses = ["new", "call", "booked", "interested", "disqualified", "do_not_call"];
  const counts = Object.fromEntries(statuses.map((status) => [status, 0]));
  for (const lead of leads) {
    if (Object.hasOwn(counts, lead.status)) counts[lead.status] += 1;
  }
  const total = leads.length;
  const center = 76;
  const radius = 66;
  let angle = -90;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No prospects</text>`);
  } else {
    const visible = statuses.filter((status) => counts[status] > 0);
    if (visible.length === 1) {
      slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${STATUS_COLOR_VARS[visible[0]]})"><title>${STATUS_LABELS[visible[0]]}: ${counts[visible[0]]}</title></circle>`);
    } else {
      for (const status of visible) {
        const nextAngle = angle + counts[status] / total * 360;
        slices.push(`<path d="${pieSlicePath(center, center, radius, angle, nextAngle)}" fill="var(${STATUS_COLOR_VARS[status]})" stroke="var(--paper)" stroke-width="2"><title>${STATUS_LABELS[status]}: ${counts[status]}</title></path>`);
        angle = nextAngle;
      }
    }
  }

  chart.setAttribute("aria-label", `Prospects by status, ${total} total`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...statuses.map((status) => {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch status-pie-${status}`;
    const label = document.createElement("span");
    label.textContent = STATUS_LABELS[status];
    const value = document.createElement("strong");
    const percent = total ? Math.round(counts[status] / total * 100) : 0;
    value.textContent = `${counts[status]} · ${percent}%`;
    item.append(swatch, label, value);
    return item;
  }));
}

function buildConnectionPieChart(allTime) {
  const chart = byId("connectionPieChart");
  const legend = byId("connectionPieLegend");
  const total = Math.max(0, Number(allTime.dials) || 0);
  const connected = Math.min(total, Math.max(0, Number(allTime.connected) || 0));
  const notConnected = total - connected;
  const center = 76;
  const radius = 66;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No dials</text>`);
  } else if (!connected || !notConnected) {
    const color = connected ? "--success" : "--amber";
    const label = connected ? "Connected" : "Not connected";
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${color})"><title>${label}: ${total}</title></circle>`);
  } else {
    const splitAngle = -90 + connected / total * 360;
    slices.push(`<path d="${pieSlicePath(center, center, radius, -90, splitAngle)}" fill="var(--success)" stroke="var(--paper)" stroke-width="2"><title>Connected: ${connected}</title></path>`);
    slices.push(`<path d="${pieSlicePath(center, center, radius, splitAngle, 270)}" fill="var(--amber)" stroke="var(--paper)" stroke-width="2"><title>Not connected: ${notConnected}</title></path>`);
  }

  chart.setAttribute("aria-label", `Dial outcomes: ${connected} connected and ${notConnected} not connected`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...[
    { label: "Connected", count: connected, className: "connection-connected" },
    { label: "Not connected", count: notConnected, className: "connection-unconnected" },
  ].map((item) => {
    const row = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch ${item.className}`;
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    const percent = total ? Math.round(item.count / total * 100) : 0;
    value.textContent = `${item.count} · ${percent}%`;
    row.append(swatch, label, value);
    return row;
  }));
}

function renderMetrics() {
  const today = state.metrics?.today || {};
  const allTime = state.metrics?.all_time || {};
  const daily = state.metrics?.daily || [];
  setText("statDialsToday", String(today.dials || 0));
  setText("statDialsAll", String(allTime.dials || 0));
  setText("statConnectedToday", String(today.connected || 0));
  setText("statConnectedAll", String(allTime.connected || 0));
  setText("statBookedToday", String(today.booked || 0));
  setText("statBookedAll", String(allTime.booked || 0));
  setText("statTalkToday", formatMinutes(today.talk_seconds));
  setText("statTalkAll", formatMinutes(allTime.talk_seconds));
  setText("statSessionConversations", String(state.session_stats?.conversations || 0));
  buildMetricsLineChart(daily);
  buildStatusPieChart(state.leads);
  buildConnectionPieChart(allTime);
}

function setDashboardTab(name, moveFocus = false) {
  const tabs = ["performance", "prospects", "pool"];
  dashboardTab = tabs.includes(name) ? name : "performance";
  const tabButtons = {
    performance: "performanceTabButton",
    prospects: "prospectsTabButton",
    pool: "poolTabButton",
  };
  const selectedButton = byId(tabButtons[dashboardTab]);
  for (const button of document.querySelectorAll("[data-dashboard-tab]")) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  for (const tab of tabs) byId(`${tab}TabPanel`).hidden = dashboardTab !== tab;
  if (dashboardTab === "prospects") renderTable();
  if (dashboardTab === "pool") renderCallerPool();
  if (moveFocus) selectedButton.focus();
}

function setPerformanceMode(mode) {
  performanceMode = mode === "all" ? "all" : "summary";
  byId("performanceTabPanel").dataset.mode = performanceMode;
  for (const button of document.querySelectorAll("[data-performance-mode]")) {
    const selected = button.dataset.performanceMode === performanceMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function render() {
  byId("headingImportButton").hidden = state.leads.length > 0;
  setText("prospectTabCount", String(state.counts?.total ?? state.leads.length));
  if (crmTableSignature() !== lastCrmTableSignature) renderTable();
  renderCallerPool();
  renderDialer();
  renderMetrics();
}

async function refreshState() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const [stateResult, metricsResult] = await Promise.all([
      request("/api/state"),
      request("/api/metrics").catch(() => null),
    ]);
    Object.assign(state, stateResult);
    if (metricsResult) state.metrics = metricsResult;
    processSensoryActivity(state.activity_log || []);
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    pollBusy = false;
  }
}

async function changeLeadStatus(lead, status, select) {
  select.disabled = true;
  byId("saveState").textContent = "Saving…";
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, { status });
    Object.assign(state, result.state);
    byId("saveState").textContent = "All changes saved";
    render();
    showToast(`${lead.name || lead.phone}: ${status === "call" ? "call scheduled for tomorrow" : STATUS_LABELS[status].toLowerCase()}`);
  } catch (error) {
    select.value = lead.status;
    select.disabled = false;
    byId("saveState").textContent = "Save failed";
    showToast(error.message, true);
  }
}

async function deleteSelectedProspects() {
  const ids = [...selectedLeadIds];
  if (!ids.length) return;
  const noun = ids.length === 1 ? "prospect" : "prospects";
  if (!window.confirm(`Delete ${ids.length} selected ${noun}? This cannot be undone.`)) return;

  const button = byId("deleteSelectedButton");
  button.disabled = true;
  byId("saveState").textContent = "Deleting…";
  const results = await Promise.allSettled(ids.map((id) => request(`/api/leads/${encodeURIComponent(id)}`, { method: "DELETE" })));
  try {
    Object.assign(state, await request("/api/state"));
    const failed = results.filter((result) => result.status === "rejected");
    if (failed.length === 0) {
      selectedLeadIds.clear();
      selectionAnchorId = null;
      byId("saveState").textContent = "All changes saved";
      render();
      showToast(`${ids.length} ${noun} deleted`);
    } else {
      byId("saveState").textContent = "Some deletions failed";
      render();
      showToast(`${ids.length - failed.length} deleted; ${failed.length} could not be deleted.`, true);
    }
  } catch (error) {
    byId("saveState").textContent = "Refresh failed";
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

async function openSettings() {
  try {
    const settings = await request("/api/settings");
    byId("accountSidInput").value = settings.account_sid || "";
    byId("authTokenInput").value = "";
    byId("authTokenInput").placeholder = settings.has_auth_token ? "Saved token, blank to keep it" : "Twilio Auth Token";
    byId("apiKeyInput").value = settings.api_key || "";
    byId("apiSecretInput").value = "";
    byId("apiSecretInput").placeholder = settings.has_api_secret ? "Saved secret, blank to keep it" : "Twilio API Key Secret";
    byId("twimlAppSidInput").value = settings.twiml_app_sid || "";
    byId("publicUrlInput").value = settings.public_base_url || "";
    byId("sessionGoalInput").value = settings.session_goal;
    byId("conversationThresholdInput").value = settings.conversation_threshold;
    byId("autoAdvanceDelayInput").value = settings.auto_advance_delay;
    byId("callingStartHourInput").value = settings.calling_start_hour;
    byId("callingEndHourInput").value = settings.calling_end_hour;
    byId("breakNudgeInput").value = settings.break_nudge_minutes;
    byId("openingScriptInput").value = settings.opening_script || "";
    byId("soundsEnabledInput").checked = settings.sounds_enabled;
    byId("soundVolumeInput").value = settings.sound_volume;
    setText("soundVolumeValue", `${settings.sound_volume}%`);
    arcadeSensory.syncControls();
    await refreshAudioDevices();
    byId("settingsDialog").showModal();
  } catch (error) {
    showToast(error.message, true);
  }
}

function setMicLevel(percent) {
  const value = Math.max(0, Math.min(100, Math.round(percent)));
  byId("microphoneLevel").setAttribute("aria-valuenow", String(value));
  byId("microphoneLevelBar").style.transform = `scaleX(${value / 100})`;
  byId("micLevelValue").textContent = `${value}%`;
  byId("micQualityStatus").textContent = value < 3 ? "Very quiet" : value > 85 ? "Very loud" : "Input active";
}

function populateAudioSelect(select, devices, kind, storageKey) {
  const saved = localStorage.getItem(storageKey) || "default";
  const options = [new Option("System default", "default")];
  let index = 0;
  for (const device of devices) {
    if (device.kind !== kind || device.deviceId === "default") continue;
    index += 1;
    const label = device.label || `${kind === "audioinput" ? "Microphone" : "Output"} ${index}`;
    options.push(new Option(label, device.deviceId));
  }
  select.replaceChildren(...options);
  select.value = options.some((option) => option.value === saved) ? saved : "default";
  localStorage.setItem(storageKey, select.value);
}

async function refreshAudioDevices(requestPermission = false) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    throw new Error("This browser does not support audio device selection.");
  }
  let permissionStream;
  try {
    if (requestPermission) permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const devices = await navigator.mediaDevices.enumerateDevices();
    populateAudioSelect(byId("audioInputSelect"), devices, "audioinput", audioInputStorageKey);
    populateAudioSelect(byId("audioOutputSelect"), devices, "audiooutput", audioOutputStorageKey);
  } finally {
    permissionStream?.getTracks().forEach((track) => track.stop());
  }
}

async function routeTestAudio(audioElement) {
  const outputId = byId("audioOutputSelect").value || "default";
  audioElement.volume = Number(byId("testVolumeInput").value) / 100;
  if (typeof audioElement.setSinkId === "function") {
    await audioElement.setSinkId(outputId);
  } else if (outputId !== "default") {
    throw new Error("This browser cannot route audio to a selected output. Try a current version of Chrome or Edge.");
  }
}

async function applyVoiceAudioDevices() {
  if (!voiceDevice?.audio) return;
  const inputId = byId("audioInputSelect").value || "default";
  const outputId = byId("audioOutputSelect").value || "default";
  if (inputId === "default" && voiceDevice.audio.inputDevice) {
    await voiceDevice.audio.unsetInputDevice();
  } else if (inputId !== "default" && voiceDevice.audio.availableInputDevices?.has(inputId)) {
    await voiceDevice.audio.setInputDevice(inputId);
  } else if (inputId !== "default") {
    throw new Error("The selected microphone is unavailable in this browser.");
  }
  if (voiceDevice.audio.isOutputSelectionSupported &&
      (outputId === "default" || voiceDevice.audio.availableOutputDevices?.has(outputId))) {
    await voiceDevice.audio.speakerDevices.set(outputId);
  } else if (outputId !== "default") {
    throw new Error("This browser cannot route call audio to a selected output device.");
  }
}

async function createVoiceDevice() {
  if (voiceDevice) return voiceDevice;
  if (!window.Twilio?.Device) {
    throw new Error("The Twilio Voice SDK did not load. Check your internet connection and reload the app.");
  }
  const { token } = await request("/api/voice-token");
  voiceDevice = new window.Twilio.Device(token, {
    codecPreferences: ["opus", "pcmu"],
    closeProtection: true,
    logLevel: 2,
  });
  voiceDevice.on("error", (error) => showToast(error.message || "Twilio audio device error.", true));
  voiceDevice.on("tokenWillExpire", async () => {
    try {
      const refreshed = await request("/api/voice-token");
      voiceDevice?.updateToken(refreshed.token);
    } catch (error) {
      showToast(error.message, true);
    }
  });
  voiceDevice.audio.on("deviceChange", () => refreshAudioDevices().catch((error) => showToast(error.message, true)));
  voiceDevice.audio.on("inputVolume", (volume) => setMicLevel(volume * 100));
  await applyVoiceAudioDevices();
  return voiceDevice;
}

async function startMicrophoneTest() {
  if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
    showToast("Microphone recording is not supported in this browser.", true);
    return;
  }
  byId("startMicTest").disabled = true;
  try {
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    micTestStream = await navigator.mediaDevices.getUserMedia({ audio });
    await refreshAudioDevices();
    micTestContext = new (window.AudioContext || window.webkitAudioContext)();
    await micTestContext.resume();
    const source = micTestContext.createMediaStreamSource(micTestStream);
    const analyser = micTestContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    micPeakLevel = 0;
    micClippingFrames = 0;
    const samples = new Float32Array(analyser.fftSize);
    const measure = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      let peak = 0;
      for (const sample of samples) {
        sum += sample * sample;
        peak = Math.max(peak, Math.abs(sample));
      }
      micPeakLevel = Math.max(micPeakLevel, peak);
      if (peak >= 0.98) micClippingFrames += 1;
      setMicLevel(Math.sqrt(sum / samples.length) * 400);
      micTestFrame = requestAnimationFrame(measure);
    };
    measure();
    micTestChunks = [];
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    micTestRecorder = new MediaRecorder(micTestStream, mimeType ? { mimeType } : undefined);
    micTestRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) micTestChunks.push(event.data);
    });
    micTestRecorder.start();
    byId("audioTestStatus").textContent = "Speak now. The level meter is live and your sample is being recorded locally.";
    byId("stopMicTest").disabled = false;
  } catch (error) {
    cancelAnimationFrame(micTestFrame);
    micTestStream?.getTracks().forEach((track) => track.stop());
    micTestStream = null;
    await micTestContext?.close();
    micTestContext = null;
    setMicLevel(0);
    byId("startMicTest").disabled = false;
    showToast(error.message || "Could not access the selected microphone.", true);
  }
}

async function stopMicrophoneTest() {
  const recorder = micTestRecorder;
  if (!recorder || recorder.state === "inactive") return;
  byId("stopMicTest").disabled = true;
  await new Promise((resolve) => {
    recorder.addEventListener("stop", resolve, { once: true });
    recorder.stop();
  });
  cancelAnimationFrame(micTestFrame);
  micTestStream?.getTracks().forEach((track) => track.stop());
  micTestStream = null;
  await micTestContext?.close();
  micTestContext = null;
  micTestRecorder = null;
  setMicLevel(0);
  byId("startMicTest").disabled = false;
  const sample = new Blob(micTestChunks, { type: recorder.mimeType || "audio/webm" });
  if (!sample.size) {
    byId("audioTestStatus").textContent = "No audio was recorded. Check microphone permission and try again.";
    return;
  }
  if (micPlaybackUrl) URL.revokeObjectURL(micPlaybackUrl);
  micPlaybackUrl = URL.createObjectURL(sample);
  const playback = byId("audioPlayback");
  playback.src = micPlaybackUrl;
  playback.hidden = false;
  await routeTestAudio(playback);
  const quality = micPeakLevel < 0.025 ? "The mic level is very low" : micClippingFrames > 2 ? "The mic is clipping" : "Mic level looks healthy";
  byId("audioTestStatus").textContent = `${quality}. Play the local sample to check clarity and headphone volume.`;
}

async function testAudioOutput() {
  let context;
  let oscillator;
  const playback = byId("outputTestPlayback");
  try {
    context = new (window.AudioContext || window.webkitAudioContext)();
    await context.resume();
    const destination = context.createMediaStreamDestination();
    playback.srcObject = destination.stream;
    await routeTestAudio(playback);
    await playback.play();
    oscillator = context.createOscillator();
    const gain = context.createGain();
    const now = context.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.04);
    gain.gain.setValueAtTime(0.18, now + 0.25);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.32);
    gain.gain.setValueAtTime(0.0001, now + 0.36);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.4);
    gain.gain.setValueAtTime(0.18, now + 0.6);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.68);
    oscillator.frequency.setValueAtTime(440, now);
    oscillator.frequency.setValueAtTime(660, now + 0.36);
    oscillator.connect(gain).connect(destination);
    oscillator.start(now);
    oscillator.stop(now + 0.72);
    byId("audioTestStatus").textContent = "Playing a two-tone output test through the selected device.";
    window.setTimeout(async () => {
      playback.pause();
      playback.srcObject = null;
      await context.close();
      byId("audioTestStatus").textContent = "Output test complete.";
    }, 800);
  } catch (error) {
    oscillator?.stop();
    playback.pause();
    playback.srcObject = null;
    await context?.close();
    showToast(error.message || "Could not play the output test.", true);
  }
}

async function importCsv(file) {
  if (!file) return;
  const button = byId("importButton");
  button.disabled = true;
  byId("headingImportButton").disabled = true;
  button.textContent = "Importing…";
  try {
    const result = await request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    Object.assign(state, result.state || {});
    setDashboardTab("prospects");
    render();
    const imported = result.import || {};
    const added = imported.added || 0;
    const duplicates = imported.duplicates || 0;
    const skipped = imported.skipped || 0;
    if (!added) {
      const reason = skipped
        ? `${skipped} row${skipped === 1 ? "" : "s"} skipped because no usable phone number was found.`
        : "No prospect rows were found in that file.";
      showToast(`Import did not add anyone. ${reason}`, true);
      return;
    }
    const extra = [
      duplicates ? `${duplicates} duplicate${duplicates === 1 ? "" : "s"} skipped` : "",
      skipped ? `${skipped} row${skipped === 1 ? "" : "s"} without a phone skipped` : "",
    ].filter(Boolean).join(" · ");
    showToast(`${added} prospect${added === 1 ? "" : "s"} added${extra ? ` · ${extra}` : ""}`);
  } catch (error) {
    console.error("CSV import failed:", error);
    showToast(error?.message || "Import failed. Check the console for details.", true);
  } finally {
    button.disabled = false;
    byId("headingImportButton").disabled = false;
    button.innerHTML = '<span class="button-symbol" aria-hidden="true">↑</span>Import CSV';
    byId("csvInput").value = "";
  }
}

async function startDialing() {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  try {
    const session = await postJson("/api/start");
    sessionStarted = true;
    const { client_call_token: clientCallToken, ...sessionState } = session;
    if (!clientCallToken) throw new Error("The browser call session could not be created.");
    Object.assign(state, sessionState);
    render();
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio });
    permissionStream.getTracks().forEach((track) => track.stop());
    await refreshAudioDevices();
    const device = await createVoiceDevice();
    await applyVoiceAudioDevices();
    voiceCall = await device.connect({
      params: { CallToken: clientCallToken },
      rtcConstraints: { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } },
    });
    voiceCall.on("disconnect", () => {
      voiceCall = null;
      drawProspectWaveform(0);
      if (voiceDevice?.audio?.unsetInputDevice) {
        voiceDevice.audio.unsetInputDevice().catch(() => {});
      }
    });
    voiceCall.on("volume", (_inputVolume, outputVolume) => drawProspectWaveform(outputVolume));
    voiceCall.on("error", (error) => showToast(error.message || "Browser call failed.", true));
    Object.assign(state, await request("/api/state"));
    render();
  } catch (error) {
    if (sessionStarted) await postJson("/api/stop").catch(() => {});
    voiceDevice?.destroy();
    voiceDevice = null;
    voiceCall = null;
    drawProspectWaveform(0);
    Object.assign(state, await request("/api/state").catch(() => ({})));
    render();
    showToast(error.message, true);
    if (!sessionStarted) openSettings();
  } finally {
    byId("startButton").disabled = state.running;
  }
}

for (const tabButton of document.querySelectorAll("[data-dashboard-tab]")) {
  tabButton.addEventListener("click", () => setDashboardTab(tabButton.dataset.dashboardTab));
  tabButton.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = ["performance", "prospects", "pool"];
    const index = tabs.indexOf(tabButton.dataset.dashboardTab);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
    const name = tabs[next];
    setDashboardTab(name, true);
  });
}
for (const modeButton of document.querySelectorAll("[data-performance-mode]")) {
  modeButton.addEventListener("click", () => setPerformanceMode(modeButton.dataset.performanceMode));
}
byId("closeTranscript").addEventListener("click", () => byId("transcriptDialog").close());
byId("downloadTranscriptButton").addEventListener("click", () => {
  const lead = state.leads.find((item) => item.id === byId("downloadTranscriptButton").dataset.leadId);
  if (lead) downloadTranscript(lead);
});
byId("transcriptDialog").addEventListener("click", (event) => {
  if (event.target === byId("transcriptDialog")) byId("transcriptDialog").close();
});
byId("settingsButton").addEventListener("click", openSettings);
byId("settingsDialog").addEventListener("close", () => {
  if (micTestRecorder?.state === "recording") {
    stopMicrophoneTest().catch((error) => showToast(error.message, true));
  }
});
byId("closeSettings").addEventListener("click", () => byId("settingsDialog").close());
byId("cancelSettings").addEventListener("click", () => byId("settingsDialog").close());
byId("settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = byId("settingsForm").querySelector("[type=submit]");
  submit.disabled = true;
  try {
    const settings = await postJson("/api/settings", {
      account_sid: byId("accountSidInput").value,
      auth_token: byId("authTokenInput").value,
      api_key: byId("apiKeyInput").value,
      api_secret: byId("apiSecretInput").value,
      twiml_app_sid: byId("twimlAppSidInput").value,
      public_base_url: byId("publicUrlInput").value,
      session_goal: byId("sessionGoalInput").value,
      conversation_threshold: byId("conversationThresholdInput").value,
      auto_advance_delay: byId("autoAdvanceDelayInput").value,
      calling_start_hour: byId("callingStartHourInput").value,
      calling_end_hour: byId("callingEndHourInput").value,
      break_nudge_minutes: byId("breakNudgeInput").value,
      opening_script: byId("openingScriptInput").value,
      sounds_enabled: byId("soundsEnabledInput").checked,
      sound_volume: byId("soundVolumeInput").value,
    });
    state.settings = settings;
    byId("authTokenInput").value = "";
    byId("apiSecretInput").value = "";
    byId("settingsDialog").close();
    render();
    showToast("Dialer settings saved");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

byId("importButton").addEventListener("click", () => byId("csvInput").click());
byId("headingImportButton").addEventListener("click", () => byId("csvInput").click());
byId("deleteSelectedButton").addEventListener("click", deleteSelectedProspects);
byId("csvInput").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) {
    console.warn("CSV file picker closed with no file selected.");
    return;
  }
  console.log(`CSV file selected: ${file.name} (${file.size} bytes, type "${file.type}")`);
  importCsv(file);
});
byId("searchInput").addEventListener("input", renderTable);
byId("statusFilter").addEventListener("change", renderTable);
byId("startButton").addEventListener("click", startDialing);
byId("pauseButton").addEventListener("click", async () => {
  try { Object.assign(state, await postJson("/api/pause")); render(); }
  catch (error) { showToast(error.message, true); }
});
byId("stopButton").addEventListener("click", async () => {
  try {
    const result = await postJson("/api/stop");
    Object.assign(state, result);
    voiceDevice?.destroy();
    voiceDevice = null;
    voiceCall = null;
    render();
    showSessionSummary(result.session_summary, result.previous_session);
  }
  catch (error) { showToast(error.message, true); }
});
byId("closeSessionSummary").addEventListener("click", () => byId("sessionSummaryDialog").close());
byId("startNewSession").addEventListener("click", () => {
  byId("sessionSummaryDialog").close();
  startDialing();
});
byId("breakPauseButton").addEventListener("click", () => {
  byId("pauseButton").click();
  byId("breakNudge").hidden = true;
});
byId("breakDismissButton").addEventListener("click", () => {
  dismissedBreakForSession = state.session_stats?.id || null;
  byId("breakNudge").hidden = true;
});
byId("soundVolumeInput").addEventListener("input", (event) => {
  setText("soundVolumeValue", `${event.target.value}%`);
});
byId("arcadeEnabledInput").addEventListener("change", (event) => arcadeSensory.updatePreferences({ enabled: event.target.checked }));
byId("arcadeReelsInput").addEventListener("change", (event) => arcadeSensory.updatePreferences({ reels: event.target.checked }));
byId("arcadeSoundInput").addEventListener("change", (event) => arcadeSensory.updatePreferences({ sound: event.target.checked }));
byId("arcadeVolumeInput").addEventListener("input", (event) => {
  setText("arcadeVolumeValue", `${event.target.value}%`);
  arcadeSensory.updatePreferences({ volume: Number(event.target.value) });
});
byId("arcadeShakeInput").addEventListener("change", (event) => arcadeSensory.updatePreferences({ shake: event.target.checked }));
byId("arcadeHapticsInput").addEventListener("change", (event) => arcadeSensory.updatePreferences({ haptics: event.target.checked }));
document.addEventListener("pointerdown", () => {
  userInteracted = true;
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  if (AudioContextType && !audioContext) audioContext = new AudioContextType();
}, { once: true });
document.addEventListener("keydown", () => {
  userInteracted = true;
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  if (AudioContextType && !audioContext) audioContext = new AudioContextType();
}, { once: true });
byId("hangupButton").addEventListener("click", async () => {
  try { Object.assign(state, await postJson("/api/hangup")); render(); }
  catch (error) { showToast(error.message, true); }
});
byId("skipVoicemailButton").addEventListener("click", async () => {
  try {
    Object.assign(state, await postJson("/api/skip"));
    showToast("Prospect skipped and marked for later");
    render();
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("enterLiveButton").addEventListener("click", async () => {
  enteringLiveLine = true;
  renderCallMonitor();
  try {
    Object.assign(state, await postJson("/api/enter-live"));
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    enteringLiveLine = false;
    renderCallMonitor();
  }
});
for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
  selector.addEventListener("change", (event) => selectTimezone(event.target.value));
}
const callDesk = document.querySelector(".dialer-run-panel");
callDesk.addEventListener("click", (event) => {
  if (!event.target.closest("button, input, select, summary, a")) callDesk.focus();
});
document.addEventListener("keydown", (event) => {
  if (!callDesk.contains(document.activeElement)) return;
  if (event.target.matches("input, textarea, select, [contenteditable=true]")) return;
  const key = event.key.toLowerCase();
  if (["1", "2", "3", "4", "5"].includes(key) && state.stage === "wrapup") {
    event.preventDefault();
    byId(["outcomeBookedButton", "outcomeCallButton", "outcomeDisqualifiedButton", "outcomeNoAnswerButton", "outcomeDncButton"][Number(key) - 1]).click();
    return;
  }
  if (event.key === " " && !event.repeat) {
    event.preventDefault();
    if (state.advance_at) byId("advanceNowButton").click();
    else if (state.running) byId("pauseButton").click();
    else byId("startButton").click();
  } else if (key === "h" && (state.active_lead || state.in_flight?.some((call) => call.state === "ringing"))) {
    event.preventDefault();
    byId("hangupButton").click();
  } else if (event.key === "Escape" && state.running) {
    event.preventDefault();
    if (!state.paused) byId("pauseButton").click();
  } else if (event.key === "?") {
    const help = document.querySelector(".shortcut-help");
    help.open = !help.open;
  }
});
async function submitOutcome(disposition, scheduledUntil = null) {
  const lead = state.pending_outcome;
  if (!lead || outcomeSubmitting) return;
  outcomeSubmitting = true;
  render();
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, {
      disposition,
      scheduled_until: scheduledUntil,
    });
    Object.assign(state, result.state);
    byId("callbackPicker").dataset.open = "";
    if (disposition === "booked") {
      celebrateBooked();
      arcadeSensory.match(lead);
    }
    showToast(`${lead.name || lead.phone}: ${disposition.replaceAll("_", " ")}`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    outcomeSubmitting = false;
    render();
  }
}
byId("outcomeCallButton").addEventListener("click", () => {
  const picker = byId("callbackPicker");
  if (picker.dataset.open) {
    byId("callbackAt").focus();
    return;
  }
  if (state.pending_outcome) byId("callbackAt").value = nextBusinessCallback(state.pending_outcome);
  byId("callbackPicker").querySelector("label").textContent = state.pending_outcome?.timezone && state.pending_outcome.timezone !== "Unknown"
    ? `Call again in ${state.pending_outcome.timezone} local time`
    : "Timezone unavailable; use your local time";
  picker.dataset.open = "true";
  renderDialer();
  byId("callbackAt").focus();
});
byId("saveCallbackButton").addEventListener("click", () => {
  try {
    const lead = state.pending_outcome;
    const timeZone = timezoneFor(lead?.timezone);
    submitOutcome("callback", localDateTimeToUtc(byId("callbackAt").value, timeZone));
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("outcomeBookedButton").addEventListener("click", () => submitOutcome("booked"));
byId("outcomeDisqualifiedButton").addEventListener("click", () => submitOutcome("not_interested"));
byId("outcomeNoAnswerButton").addEventListener("click", () => submitOutcome("no_answer"));
byId("outcomeDncButton").addEventListener("click", () => submitOutcome("do_not_call"));
byId("advanceNowButton").addEventListener("click", async () => {
  try { Object.assign(state, await postJson("/api/advance")); render(); }
  catch (error) { showToast(error.message, true); }
});
byId("refreshAudioDevices").addEventListener("click", async () => {
  try {
    await refreshAudioDevices(true);
    await applyVoiceAudioDevices();
    showToast("Audio devices refreshed");
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("audioInputSelect").addEventListener("change", async (event) => {
  localStorage.setItem(audioInputStorageKey, event.target.value);
  try {
    if (micTestRecorder?.state === "recording") await stopMicrophoneTest();
    await applyVoiceAudioDevices();
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("audioOutputSelect").addEventListener("change", async (event) => {
  localStorage.setItem(audioOutputStorageKey, event.target.value);
  try {
    await applyVoiceAudioDevices();
    await routeTestAudio(byId("audioPlayback"));
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("startMicTest").addEventListener("click", startMicrophoneTest);
byId("stopMicTest").addEventListener("click", () => stopMicrophoneTest().catch((error) => showToast(error.message, true)));
byId("outputTestButton").addEventListener("click", testAudioOutput);
byId("testVolumeInput").addEventListener("input", (event) => {
  const value = Number(event.target.value);
  byId("testVolumeValue").textContent = `${value}%`;
  byId("audioPlayback").volume = value / 100;
  byId("outputTestPlayback").volume = value / 100;
});
if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener("devicechange", () => refreshAudioDevices().catch(() => {}));
}
function showLoginGate(message) {
  const gate = byId("loginGate");
  const error = byId("loginError");
  gate.hidden = false;
  document.querySelector(".app-shell")?.setAttribute("hidden", "hidden");
  if (message) {
    error.hidden = false;
    error.textContent = message;
  } else {
    error.hidden = true;
  }
}

function hideLoginGate() {
  byId("loginGate").hidden = true;
  document.querySelector(".app-shell")?.removeAttribute("hidden");
}

function syncAccountChrome(session) {
  const email = session?.user?.email || "";
  const emailEl = byId("accountEmail");
  const signOut = byId("signOutButton");
  emailEl.hidden = !email;
  signOut.hidden = !googleAuthEnabled;
  emailEl.textContent = email;
}

async function bootApp() {
  hideLoginGate();
  drawProspectWaveform(0);
  refreshState();
  request("/api/settings").then((settings) => {
    if (!settings.account_sid || !settings.has_auth_token || !settings.api_key || !settings.has_api_secret || !settings.twiml_app_sid || !settings.public_base_url) {
      showToast("Complete your Twilio Voice credentials and callback URL in Settings to start dialing.");
    }
  }).catch(() => {});
}

async function initAuth() {
  const config = await fetch("/api/auth/config").then((response) => response.json());
  googleAuthEnabled = Boolean(config.google && window.supabase?.createClient);
  if (!googleAuthEnabled) {
    await bootApp();
    return;
  }
  supabaseClient = window.supabase.createClient(config.url, config.anonKey);
  supabaseClient.auth.onAuthStateChange((_event, session) => {
    accessToken = session?.access_token || null;
    syncAccountChrome(session);
  });
  const { data: { session } } = await supabaseClient.auth.getSession();
  accessToken = session?.access_token || null;
  syncAccountChrome(session);
  if (session) {
    await bootApp();
    return;
  }
  showLoginGate();
}

byId("googleSignInButton").addEventListener("click", async () => {
  if (!supabaseClient) return;
  const { error } = await supabaseClient.auth.signInWithOAuth({
    provider: "google",
    options: { redirectTo: window.location.origin + "/" },
  });
  if (error) showLoginGate(error.message);
});
byId("signOutButton").addEventListener("click", async () => {
  accessToken = null;
  await supabaseClient?.auth.signOut();
  showLoginGate();
});

initAuth().catch((error) => showLoginGate(error.message || "Could not start sign-in."));
setInterval(() => { if (!byId("loginGate").hidden) return; refreshState(); }, 1500);