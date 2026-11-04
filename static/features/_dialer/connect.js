import { debugEvent, postJson, request } from "../../_core/api.js";
import { createVoiceDevice, destroyVoiceDevice, takeLatestVoiceError } from "./_voice/connect.js";
import { applyVoiceAudioDevices, refreshAudioDevices } from "./_voice/devices.js";
import { S, state } from "../../_core/state.js";
import { loadAppState, mergeLiveState, refreshLeadsIfStale } from "../../_core/sync-state.js";
import { render } from "../../core.js";
import { byId } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { errorText, showToast } from "../../_core/notify.js";
import { drawProspectWaveform, startProspectWaveform, stopProspectWaveform } from "./card.js";

let connectGeneration = 0;
let rejoinTimer = null;

export function prospectLabel(lead) {
  return lead?.name || lead?.business || formatPhoneNumber(lead?.phone) || "Prospect";
}

function waitForCallReady(call, timeoutMs) {
  return new Promise((resolve, reject) => {
    const status = call?.status?.();
    if (status === "open" || status === "connected") {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      cleanup();
      reject(new Error("Computer audio did not connect in time. Check Settings → public HTTPS URL and that the hook server is reachable."));
    }, timeoutMs);
    const onAccept = () => { cleanup(); resolve(); };
    const onError = (error) => { cleanup(); reject(error); };
    const onDisconnect = () => {
      cleanup();
      reject(new Error("Computer audio disconnected before the conference connected."));
    };
    const cleanup = () => {
      clearTimeout(timer);
      call?.off?.("accept", onAccept);
      call?.off?.("error", onError);
      call?.off?.("disconnect", onDisconnect);
    };
    call?.on?.("accept", onAccept);
    call?.on?.("error", onError);
    call?.on?.("disconnect", onDisconnect);
  });
}

function waitForDisconnect(call, timeoutMs) {
  return new Promise((resolve) => {
    if (!call || call.status?.() === "closed") {
      resolve();
      return;
    }
    const timer = setTimeout(resolve, timeoutMs);
    call.once("disconnect", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

export async function tearDownVoice({ intentional = false } = {}) {
  connectGeneration += 1;
  clearTimeout(rejoinTimer);
  S.expectVoiceDisconnect = intentional;
  try {
    if (S.voiceCall) {
      S.voiceCall.disconnect();
      await waitForDisconnect(S.voiceCall, 2500);
    }
  } catch (error) {
    debugEvent("error", "voice disconnect", errorText(error, ""));
  }
  S.voiceCall = null;
  await destroyVoiceDevice();
  stopProspectWaveform();
  S.expectVoiceDisconnect = false;
}

function bindVoiceCallHandlers(call) {
  call.on("accept", () => startProspectWaveform(S.voiceCall));
  call.on("disconnect", () => {
    S.voiceCall = null;
    stopProspectWaveform();
    if (S.voiceDevice?.audio?.unsetInputDevice) {
      S.voiceDevice.audio.unsetInputDevice().catch(() => {});
    }
    if (!S.expectVoiceDisconnect && state.running) {
      document.dispatchEvent(new CustomEvent("voice-leg-lost"));
    }
  });
  call.on("volume", (_inputVolume, outputVolume) => {
    if (!S.waveformAnalyser) drawProspectWaveform(outputVolume);
  });
  call.on("error", (error) => {
    debugEvent("error", "browser call", errorText(error, "Browser call failed."));
    showToast(errorText(error, "Browser call failed."), true);
  });
}

export async function connectBrowserCall(clientCallToken, { freshDevice = false } = {}) {
  if (!clientCallToken) throw new Error("Missing browser call token.");
  const generation = ++connectGeneration;
  S.voiceConnectBusy = true;
  try {
    if (freshDevice) await tearDownVoice({ intentional: true });
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    let permissionStream;
    try {
      permissionStream = await navigator.mediaDevices.getUserMedia({ audio });
    } catch (error) {
      if (inputId === "default") throw error;
      debugEvent("error", "mic fallback", errorText(error, "Microphone permission failed."));
      permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    }
    permissionStream.getTracks().forEach((track) => track.stop());
    await refreshAudioDevices();
    const device = await createVoiceDevice({ fresh: freshDevice });
    if (generation !== connectGeneration) {
      throw new Error("Voice connect cancelled.");
    }
    await applyVoiceAudioDevices();
    S.voiceCall = await device.connect({
      params: { DeskToken: clientCallToken },
      rtcConstraints: { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } },
    });
    if (generation !== connectGeneration) {
      S.voiceCall?.disconnect();
      S.voiceCall = null;
      throw new Error("Voice connect cancelled.");
    }
    bindVoiceCallHandlers(S.voiceCall);
    startProspectWaveform(S.voiceCall);
    await waitForCallReady(S.voiceCall, 28000);
    if (generation !== connectGeneration) {
      throw new Error("Voice connect cancelled.");
    }
  } finally {
    S.voiceConnectBusy = false;
  }
}

export async function connectAndCleanup(clientCallToken, sessionState) {
  mergeLiveState(sessionState);
  await refreshLeadsIfStale(sessionState.leads_version);
  render();
  try {
    await connectBrowserCall(clientCallToken, { freshDevice: true });
  } catch (error) {
    await postJson("/api/stop").catch(() => {});
    await tearDownVoice({ intentional: true });
    await loadAppState().catch(() => {});
    render();
    const signaled = errorText(takeLatestVoiceError(), "");
    const message = errorText(error, "") || signaled || "The browser call could not connect.";
    debugEvent("error", "voice connect", message);
    showToast(message, true);
    return error;
  }
  await loadAppState();
  render();
  return null;
}

export async function maybeRejoinVoice() {
  const urgent = S.voiceRejoinPending;
  S.voiceRejoinPending = false;
  if (
    S.voiceRejoinBusy
    || S.voiceConnectBusy
    || S.expectVoiceDisconnect
    || !state.running
    || state.agent_ready
    || S.voiceCall
    || state.pending_outcome
  ) {
    return;
  }
  if (!urgent && Date.now() - (S.lastVoiceRejoinAt || 0) < 10000) return;
  S.voiceRejoinBusy = true;
  S.lastVoiceRejoinAt = Date.now();
  try {
    const payload = await postJson("/api/voice/rejoin");
    const token = payload.client_call_token;
    if (!token) return;
    mergeLiveState(payload);
    await connectBrowserCall(token, { freshDevice: true });
    await loadAppState().catch(() => {});
    render();
  } catch (error) {
    const message = errorText(error, "") || errorText(takeLatestVoiceError(), "");
    if (message) debugEvent("error", "voice rejoin", message);
  } finally {
    S.voiceRejoinBusy = false;
  }
}

export function scheduleVoiceRejoin(delayMs = 1200) {
  clearTimeout(rejoinTimer);
  rejoinTimer = setTimeout(() => {
    maybeRejoinVoice().catch(() => {});
  }, delayMs);
}

document.addEventListener("voice-leg-lost", () => {
  S.voiceRejoinPending = true;
  scheduleVoiceRejoin(800);
});
