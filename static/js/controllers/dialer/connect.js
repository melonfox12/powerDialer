import { debugEvent } from "../../../_core/api.js";
import { applyVoiceAudioDevices, createVoiceDevice, refreshAudioDevices } from "../../features/voice/device/index.js";
import { S } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";
import { formatPhoneNumber } from "../../../_core/phone.js";
import { showToast } from "../../../_core/notify.js";
import { drawProspectWaveform, startProspectWaveform, stopProspectWaveform } from "../../views/dialer/card.js";

export function prospectLabel(lead) {
  return lead?.name || lead?.business || formatPhoneNumber(lead?.phone) || "Prospect";
}

export async function connectBrowserCall(clientCallToken) {
  const inputId = byId("audioInputSelect").value || "default";
  const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
  let permissionStream;
  try {
    permissionStream = await navigator.mediaDevices.getUserMedia({ audio });
  } catch (error) {
    if (inputId === "default") throw error;
    debugEvent("error", "mic fallback", error.message);
    permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  }
  permissionStream.getTracks().forEach((track) => track.stop());
  await refreshAudioDevices();
  const device = await createVoiceDevice();
  await applyVoiceAudioDevices();
  S.voiceCall = await device.connect({
    params: { CallToken: clientCallToken },
    rtcConstraints: { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } },
  });
  S.voiceCall.on("accept", () => startProspectWaveform(S.voiceCall));
  S.voiceCall.on("disconnect", () => {
    S.voiceCall = null;
    stopProspectWaveform();
    if (S.voiceDevice?.audio?.unsetInputDevice) {
      S.voiceDevice.audio.unsetInputDevice().catch(() => {});
    }
  });
  S.voiceCall.on("volume", (_inputVolume, outputVolume) => {
    if (!S.waveformAnalyser) drawProspectWaveform(outputVolume);
  });
  startProspectWaveform(S.voiceCall);
  S.voiceCall.on("error", (error) => showToast(error.message || "Browser call failed.", true));
}
