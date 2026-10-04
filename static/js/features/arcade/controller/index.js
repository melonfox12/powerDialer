import { AudioMixin } from "../audio.js";
import { ParticlesMixin } from "../particles.js";
import { ReelsMixin } from "../reels.js";
import { PlaybackMixin } from "./playback.js";
import { ArcadeCore } from "./shell.js";

export const ArcadeSensoryController = ParticlesMixin(ReelsMixin(AudioMixin(PlaybackMixin(ArcadeCore))));
export let arcadeSensory = null;
export function startArcade() {
  arcadeSensory = new ArcadeSensoryController();
}
