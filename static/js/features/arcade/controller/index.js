import { AudioMixin } from "../fx/audio.js";
import { ParticlesMixin } from "../fx/particles.js";
import { ReelsMixin } from "../fx/reels.js";
import { PlaybackMixin } from "./playback.js";
import { ArcadeCore } from "./shell.js";

export const ArcadeSensoryController = ParticlesMixin(ReelsMixin(AudioMixin(PlaybackMixin(ArcadeCore))));
export let arcadeSensory = null;
export function startArcade() {
  arcadeSensory = new ArcadeSensoryController();
}
