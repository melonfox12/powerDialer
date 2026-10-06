import { S, state } from "../../../../_core/state.js";
import { byId } from "../../../../_core/format.js";

export function celebrateBooked() {
  const stage = byId("callStage");
  stage.classList.remove("booked-celebration");
  void stage.offsetWidth;
  stage.classList.add("booked-celebration");
  playCue("booked");
}

export function playCue(kind) {
  if (!S.userInteracted || state.settings?.sounds_enabled === false) return;
  const volume = Number(state.settings?.sound_volume ?? 35) / 100 * 0.07;
  if (volume <= 0) return;
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextType) return;
  if (!S.audioContext) S.audioContext = new AudioContextType();
  if (S.audioContext.state === "suspended") S.audioContext.resume().catch((error) => console.warn("Audio cue could not resume:", error));
  const now = S.audioContext.currentTime;
  const notes = kind === "booked" ? [880, 1174.66, 1396.91] : [660];
  notes.forEach((frequency, index) => {
    const oscillator = S.audioContext.createOscillator();
    const gain = S.audioContext.createGain();
    const start = now + index * (kind === "booked" ? 0.09 : 0);
    oscillator.type = "sine";
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(volume, start + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.001, start + (kind === "booked" ? 0.14 : 0.1));
    oscillator.connect(gain);
    gain.connect(S.audioContext.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.15);
  });
}

export const AudioMixin = (Base) => class extends Base {
  canPlaySound() {
    return S.userInteracted && this.preferences.enabled && this.preferences.sound &&
      state.settings?.sounds_enabled !== false && this.preferences.volume > 0;
  }

  playTick(frequency) {
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType || !this.canPlaySound()) return;
    if (!S.audioContext) S.audioContext = new AudioContextType();
    if (S.audioContext.state === "suspended") {
      S.audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const now = S.audioContext.currentTime;
    const oscillator = S.audioContext.createOscillator();
    const gain = S.audioContext.createGain();
    oscillator.type = "square";
    oscillator.frequency.setValueAtTime(frequency, now);
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.exponentialRampToValueAtTime(this.preferences.volume / 100 * 0.035, now + 0.003);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.022);
    oscillator.connect(gain);
    gain.connect(S.audioContext.destination);
    oscillator.start(now);
    oscillator.stop(now + 0.025);
  }

  playRewardChime() {
    if (!this.canPlaySound()) return;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType) return;
    if (!S.audioContext) S.audioContext = new AudioContextType();
    if (S.audioContext.state === "suspended") {
      S.audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const notes = [523.25, 659.25, 783.99, 1046.5];
    const volume = this.preferences.volume / 100 * 0.07;
    notes.forEach((frequency, index) => {
      const oscillator = S.audioContext.createOscillator();
      const gain = S.audioContext.createGain();
      const start = S.audioContext.currentTime + index * 0.085;
      oscillator.type = "triangle";
      oscillator.frequency.setValueAtTime(frequency, start);
      gain.gain.setValueAtTime(0.0001, start);
      gain.gain.exponentialRampToValueAtTime(volume, start + 0.012);
      gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.16);
      oscillator.connect(gain);
      gain.connect(S.audioContext.destination);
      oscillator.start(start);
      oscillator.stop(start + 0.17);
    });
  }

  playResetTone() {
    if (!this.canPlaySound()) return;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextType) return;
    if (!S.audioContext) S.audioContext = new AudioContextType();
    if (S.audioContext.state === "suspended") {
      S.audioContext.resume().catch((error) => console.warn("Arcade audio could not resume:", error));
    }
    const now = S.audioContext.currentTime;
    const oscillator = S.audioContext.createOscillator();
    const gain = S.audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.setValueAtTime(80, now);
    oscillator.frequency.linearRampToValueAtTime(40, now + 0.3);
    gain.gain.setValueAtTime(this.preferences.volume / 100 * 0.08, now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.32);
    oscillator.connect(gain);
    gain.connect(S.audioContext.destination);
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
};
