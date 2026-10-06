import { byId, setText } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";

export function construct(arcade) {
    arcade.preferencesKey = "prospect-desk-arcade-profile";
    arcade.defaults = { enabled: true, reels: true, sound: true, volume: 35, shake: true, haptics: true };
    arcade.preferences = arcade.loadPreferences();
    arcade.viewport = byId("arcadeViewport");
    arcade.reelWindows = [...arcade.viewport.querySelectorAll(".arcade-reel-window")];
    arcade.reels = arcade.reelWindows.map((windowElement) => {
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
    arcade.canvas = byId("arcadeParticles");
    arcade.context = arcade.canvas.getContext("2d");
    arcade.particles = [];
    arcade.particleFrame = 0;
    arcade.tickTimer = 0;
    arcade.tickCount = 0;
    arcade.timeouts = new Set();
    arcade.phase = "idle";
    arcade.activeLeadKey = null;
    arcade.lastMatchKey = null;
    arcade.pendingSpinKey = null;
    arcade.valueAnimation = 0;
    arcade.viewport.hidden = true;
    arcade.syncControls();
    window.addEventListener("resize", () => arcade.resizeCanvas());
    arcade.resizeCanvas();
  }

export function loadPreferences(arcade) {
    try {
      const saved = JSON.parse(localStorage.getItem(arcade.preferencesKey) || "{}");
      const volume = Number(saved.volume ?? arcade.defaults.volume);
      return {
        ...arcade.defaults,
        ...saved,
        enabled: saved.enabled ?? arcade.defaults.enabled,
        reels: saved.reels ?? arcade.defaults.reels,
        sound: saved.sound ?? arcade.defaults.sound,
        shake: saved.shake ?? arcade.defaults.shake,
        haptics: saved.haptics ?? arcade.defaults.haptics,
        volume: Number.isFinite(volume) ? Math.max(0, Math.min(100, volume)) : arcade.defaults.volume,
      };
    } catch (error) {
      console.warn("Arcade profile could not be loaded:", error);
      return { ...arcade.defaults };
    }
  }

export function syncControls(arcade) {
    byId("arcadeEnabledInput").checked = arcade.preferences.enabled;
    byId("arcadeReelsInput").checked = arcade.preferences.reels;
    byId("arcadeSoundInput").checked = arcade.preferences.sound;
    byId("arcadeVolumeInput").value = arcade.preferences.volume;
    byId("arcadeShakeInput").checked = arcade.preferences.shake;
    byId("arcadeHapticsInput").checked = arcade.preferences.haptics;
    setText("arcadeVolumeValue", `${arcade.preferences.volume}%`);
    arcade.viewport.classList.toggle("arcade-reels-disabled", !arcade.preferences.reels);
  }

export function updatePreferences(arcade, changes) {
    arcade.preferences = { ...arcade.preferences, ...changes };
    if (!arcade.preferences.enabled) arcade.stop();
    else if (!arcade.canPlaySound()) arcade.stopTicking();
    else if (arcade.phase === "spinning") arcade.startTicking();
    arcade.syncControls();
    try {
      localStorage.setItem(arcade.preferencesKey, JSON.stringify(arcade.preferences));
    } catch (error) {
      console.error("Arcade profile could not be saved:", error);
      showToast("Arcade profile could not be saved in this browser.", true);
    }
  }

export function schedule(arcade, callback, delay) {
    const timer = setTimeout(() => {
      arcade.timeouts.delete(timer);
      callback();
    }, delay);
    arcade.timeouts.add(timer);
    return timer;
  }

export function clearTimers(arcade) {
    clearInterval(arcade.tickTimer);
    arcade.tickTimer = 0;
    for (const timer of arcade.timeouts) clearTimeout(timer);
    arcade.timeouts.clear();
    document.querySelector(".dialer-run-panel").classList.remove("arcade-failure-flash", "arcade-shake");
  }

export function stop(arcade) {
    arcade.clearTimers();
    arcade.stopParticles();
    arcade.valueAnimation += 1;
    arcade.phase = "idle";
    arcade.viewport.hidden = true;
    arcade.viewport.classList.remove("is-resetting", "is-near-miss", "is-match");
    for (const windowElement of arcade.reelWindows) {
      windowElement.classList.remove("is-spinning", "is-locking", "is-near-miss");
    }
  }
