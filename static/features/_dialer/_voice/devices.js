import { S, audioInputStorageKey, audioOutputStorageKey } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";

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
