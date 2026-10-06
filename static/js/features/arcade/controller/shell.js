import { byId, setText } from "../../../../_core/format.js";
import { showToast } from "../../../../_core/notify.js";

export class ArcadeCore {
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
}
