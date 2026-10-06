import { request } from "../../../../_core/api.js";
import { S, audioInputStorageKey, audioOutputStorageKey } from "../../../../_core/state.js";
import { byId } from "../../../../_core/format.js";
import { showToast } from "../../../../_core/notify.js";
import { startMicrophoneTest, stopMicrophoneTest, testAudioOutput } from "../testing/index.js";
import { applyVoiceAudioDevices, refreshAudioDevices, routeTestAudio, setMicLevel } from "./devices.js";

export async function createVoiceDevice() {
  if (S.voiceDevice) return S.voiceDevice;
  if (!window.Twilio?.Device) {
    throw new Error("The Twilio Voice SDK did not load. Check your internet connection and reload the app.");
  }
  const { token } = await request("/api/voice-token");
  S.voiceDevice = new window.Twilio.Device(token, {
    codecPreferences: ["opus", "pcmu"],
    closeProtection: true,
    logLevel: 2,
  });
  S.voiceDevice.on("error", (error) => showToast(error.message || "Twilio audio device error.", true));
  S.voiceDevice.on("tokenWillExpire", async () => {
    try {
      const refreshed = await request("/api/voice-token");
      S.voiceDevice?.updateToken(refreshed.token);
    } catch (error) {
      showToast(error.message, true);
    }
  });
  S.voiceDevice.audio.on("deviceChange", () => refreshAudioDevices().catch((error) => showToast(error.message, true)));
  S.voiceDevice.audio.on("inputVolume", (volume) => setMicLevel(volume * 100));
  await applyVoiceAudioDevices();
  return S.voiceDevice;
}


export function bindVoice() {
  document.addEventListener("pointerdown", () => {
    S.userInteracted = true;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (AudioContextType && !S.audioContext) S.audioContext = new AudioContextType();
  }, { once: true });
  document.addEventListener("keydown", () => {
    S.userInteracted = true;
    const AudioContextType = window.AudioContext || window.webkitAudioContext;
    if (AudioContextType && !S.audioContext) S.audioContext = new AudioContextType();
  }, { once: true });
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
      if (S.micTestRecorder?.state === "recording") await stopMicrophoneTest();
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
}
