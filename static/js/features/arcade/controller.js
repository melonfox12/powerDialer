import { byId, setText } from "../../utils/format.js";
import { showToast } from "../../views/dialogs.js";
import { AudioMixin } from "./audio.js";
import { ParticlesMixin } from "./particles.js";
import { ReelsMixin } from "./reels.js";

class ArcadeCore {
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

  reset(quiet = false) {
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
    this.viewport.querySelector("#arcadeValue").hidden = true;
    if (quiet) {
      this.viewport.classList.remove("is-near-miss", "is-resetting");
      setText("arcadeStatus", "Call ended");
      this.schedule(() => {
        this.viewport.classList.add("is-resetting");
        this.schedule(() => {
          this.viewport.classList.remove("is-resetting");
          this.phase = "idle";
          this.viewport.hidden = true;
        }, 270);
      }, 150);
      return;
    }
    this.viewport.classList.add("is-near-miss");
    this.viewport.classList.remove("is-resetting");
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
}


export const ArcadeSensoryController = ParticlesMixin(ReelsMixin(AudioMixin(ArcadeCore)));
export let arcadeSensory = null;
export function startArcade() {
  arcadeSensory = new ArcadeSensoryController();
}
