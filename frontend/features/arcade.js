import { celebrateBooked, canPlaySound, playCue, playResetTone, playRewardChime, playTick, vibrate } from "./_arcade/audio.js";
import { burstParticles, drawParticles, resizeCanvas, stopParticles } from "./_arcade/particles.js";
import { animateValue, flashFailure, reset } from "./_arcade/playback.js";
import { match, startSpin, startTicking, stopTicking } from "./_arcade/reels.js";
import {
  clearTimers,
  construct,
  loadPreferences,
  schedule,
  stop,
  syncControls,
  updatePreferences,
} from "./_arcade/shell.js";

export { celebrateBooked, playCue };

export class ArcadeSensoryController {
  constructor() { construct(this); }
  loadPreferences() { return loadPreferences(this); }
  syncControls() { syncControls(this); }
  updatePreferences(changes) { updatePreferences(this, changes); }
  schedule(callback, delay) { return schedule(this, callback, delay); }
  clearTimers() { clearTimers(this); }
  stop() { stop(this); }
  animateValue(target, element, animationId) { animateValue(this, target, element, animationId); }
  reset(quiet = false) { reset(this, quiet); }
  flashFailure() { flashFailure(this); }
  canPlaySound() { return canPlaySound(this); }
  playTick(frequency) { playTick(this, frequency); }
  playRewardChime() { playRewardChime(this); }
  playResetTone() { playResetTone(this); }
  vibrate(pattern) { vibrate(this, pattern); }
  stopTicking() { stopTicking(this); }
  startSpin(leadKey) { startSpin(this, leadKey); }
  startTicking() { startTicking(this); }
  match(lead) { match(this, lead); }
  resizeCanvas() { resizeCanvas(this); }
  burstParticles() { burstParticles(this); }
  drawParticles() { drawParticles(this); }
  stopParticles() { stopParticles(this); }
}

export let arcadeSensory = null;
export function startArcade() {
  arcadeSensory = new ArcadeSensoryController();
}
