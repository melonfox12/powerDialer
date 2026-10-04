import { request } from "../../api/client.js";
import { S, audioInputStorageKey, audioOutputStorageKey, state } from "../../store/state.js";
import { byId } from "../../utils/format.js";
import { showToast } from "../../views/dialogs.js";
import { startMicrophoneTest, stopMicrophoneTest, testAudioOutput } from "./testing.js";

export function setMicLevel(percent) {
  const value = Math.max(0, Math.min(100, Math.round(percent)));
  byId("microphoneLevel").setAttribute("aria-valuenow", String(value));
  byId("microphoneLevelBar").style.transform = `scaleX(${value / 100})`;
  byId("micLevelValue").textContent = `${value}%`;
  byId("micQualityStatus").textContent = value < 3 ? "Very quiet" : value > 85 ? "Very loud" : "Input active";
}

export function populateAudioSelect(select, devices, kind, storageKey) {
  const saved = localStorage.getItem(storageKey) || "default";
  const options = [new Option("System default", "default")];
  let index = 0;
  for (const device of devices) {
    if (device.kind !== kind || device.deviceId === "default") continue;
    index += 1;
    const label = device.label || `${kind === "audioinput" ? "Microphone" : "Output"} ${index}`;
    options.push(new Option(label, device.deviceId));
  }
  select.replaceChildren(...options);
  select.value = options.some((option) => option.value === saved) ? saved : "default";
  localStorage.setItem(storageKey, select.value);
}

export async function refreshAudioDevices(requestPermission = false) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    throw new Error("This browser does not support audio device selection.");
  }
  let permissionStream;
  try {
    if (requestPermission) permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const devices = await navigator.mediaDevices.enumerateDevices();
    populateAudioSelect(byId("audioInputSelect"), devices, "audioinput", audioInputStorageKey);
    populateAudioSelect(byId("audioOutputSelect"), devices, "audiooutput", audioOutputStorageKey);
  } finally {
    permissionStream?.getTracks().forEach((track) => track.stop());
  }
}

export async function routeTestAudio(audioElement) {
  const outputId = byId("audioOutputSelect").value || "default";
  audioElement.volume = Number(byId("testVolumeInput").value) / 100;
  if (typeof audioElement.setSinkId === "function") {
    await audioElement.setSinkId(outputId);
  } else if (outputId !== "default") {
    throw new Error("This browser cannot route audio to a selected output. Try a current version of Chrome or Edge.");
  }
}

export function twilioHasDevice(collection, id) {
  if (!collection || !id) return false;
  if (typeof collection.has === "function") return collection.has(id);
  return Object.prototype.hasOwnProperty.call(collection, id);
}

export function twilioDeviceEntries(collection) {
  if (!collection) return [];
  if (typeof collection.entries === "function") return [...collection.entries()];
  return Object.entries(collection);
}

export function resolveTwilioDeviceId(collection, selectedId, selectId) {
  if (!selectedId || selectedId === "default") return "";
  if (twilioHasDevice(collection, selectedId)) return selectedId;
  const label = (byId(selectId)?.selectedOptions?.[0]?.textContent || "").trim().toLowerCase();
  if (!label) return "";
  for (const [id, info] of twilioDeviceEntries(collection)) {
    if (!id || id === "default" || id === "communications") continue;
    const name = String(info?.label || "").trim().toLowerCase();
    if (name && (name === label || name.includes(label) || label.includes(name))) return id;
  }
  return "";
}

export function waitForTwilioAudioDevices(device, timeoutMs = 2500) {
  const audio = device?.audio;
  if (!audio) return Promise.resolve();
  if (audio.availableInputDevices?.size || audio.availableOutputDevices?.size) return Promise.resolve();
  return new Promise((resolve) => {
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (typeof audio.removeListener === "function") audio.removeListener("deviceChange", onChange);
      resolve();
    };
    const onChange = () => {
      if (audio.availableInputDevices?.size || audio.availableOutputDevices?.size) finish();
    };
    const timer = setTimeout(finish, timeoutMs);
    audio.on("deviceChange", onChange);
    onChange();
  });
}

export async function applyVoiceAudioDevices() {
  if (!S.voiceDevice?.audio) return;
  await waitForTwilioAudioDevices(S.voiceDevice);
  const inputId = byId("audioInputSelect").value || "default";
  const outputId = byId("audioOutputSelect").value || "default";
  const resolvedInput = resolveTwilioDeviceId(S.voiceDevice.audio.availableInputDevices, inputId, "audioInputSelect");
  if (resolvedInput) {
    await S.voiceDevice.audio.setInputDevice(resolvedInput);
  } else if (S.voiceDevice.audio.inputDevice) {
    await S.voiceDevice.audio.unsetInputDevice();
  }
  if (!S.voiceDevice.audio.isOutputSelectionSupported) return;
  const resolvedOutput = resolveTwilioDeviceId(S.voiceDevice.audio.availableOutputDevices, outputId, "audioOutputSelect");
  if (resolvedOutput) await S.voiceDevice.audio.speakerDevices.set(resolvedOutput);
}

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
