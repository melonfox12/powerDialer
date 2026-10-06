import { registerAudioDevices } from "../../../../core.js";
import { refreshAudioDevices } from "./devices.js";
import { stopMicrophoneTest } from "../testing/index.js";

registerAudioDevices(refreshAudioDevices, stopMicrophoneTest);

export {
  applyVoiceAudioDevices,
  populateAudioSelect,
  refreshAudioDevices,
  resolveTwilioDeviceId,
  routeTestAudio,
  setMicLevel,
  twilioDeviceEntries,
  twilioHasDevice,
  waitForTwilioAudioDevices,
} from "./devices.js";
export { bindVoice, createVoiceDevice } from "./connect.js";
