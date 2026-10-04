import { debugEvent, postJson, request } from "../api/client.js";
import { applyVoiceAudioDevices, createVoiceDevice, refreshAudioDevices } from "../features/voice/device/index.js";
import { S, state } from "../store/state.js";
import { byId } from "../utils/format.js";
import { showToast } from "../utils/notify.js";
import { renderCallMonitor } from "../views/monitor/index.js";
import { setStartNewSession, showSessionSummary } from "../views/dialogs/index.js";
import { drawProspectWaveform, startProspectWaveform, stopProspectWaveform } from "../views/dialer/card.js";
import { render } from "../views/render.js";
import { selectTimezone } from "./pool.js";
import { openSettings } from "./settings.js";

setStartNewSession(startDialing);

export async function startDialing() {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  try {
    const session = await postJson("/api/start");
    sessionStarted = true;
    const { client_call_token: clientCallToken, ...sessionState } = session;
    if (!clientCallToken) throw new Error("The browser call session could not be created.");
    Object.assign(state, sessionState);
    render();
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
    Object.assign(state, await request("/api/state"));
    render();
  } catch (error) {
    if (sessionStarted) await postJson("/api/stop").catch(() => {});
    S.voiceDevice?.destroy();
    S.voiceDevice = null;
    S.voiceCall = null;
    stopProspectWaveform();
    Object.assign(state, await request("/api/state").catch(() => ({})));
    render();
    showToast(error.message, true);
    if (!sessionStarted) openSettings();
  } finally {
    byId("startButton").disabled = state.running;
  }
}

export function bindDialer() {
  byId("startButton").addEventListener("click", startDialing);
  byId("pauseButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/pause")); render(); }
    catch (error) { showToast(error.message, true); }
  });
  byId("stopButton").addEventListener("click", async () => {
    try {
      const result = await postJson("/api/stop");
      Object.assign(state, result);
      S.voiceDevice?.destroy();
      S.voiceDevice = null;
      S.voiceCall = null;
      stopProspectWaveform();
      render();
      showSessionSummary(result.session_summary, result.previous_session);
    }
    catch (error) { showToast(error.message, true); }
  });
  byId("hangupButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/hangup")); render(); }
    catch (error) { showToast(error.message, true); }
  });
  byId("keepLineButton").addEventListener("click", () => {
    if (!state.active_lead) return;
    S.keptLineId = state.active_lead.id;
    showToast("Staying on the line");
    renderCallMonitor();
  });
  byId("skipVoicemailButton").addEventListener("click", async () => {
    try {
      Object.assign(state, await postJson("/api/skip"));
      showToast("Skipped. Choose an outcome.");
      render();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  byId("enterLiveButton").addEventListener("click", async () => {
    S.enteringLiveLine = true;
    renderCallMonitor();
    try {
      Object.assign(state, await postJson("/api/enter-live"));
      render();
    } catch (error) {
      showToast(error.message, true);
    } finally {
      S.enteringLiveLine = false;
      renderCallMonitor();
    }
  });
  for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
    selector.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
  const callDesk = document.querySelector(".dialer-run-panel");
  callDesk.addEventListener("click", (event) => {
    if (!event.target.closest("button, input, select, summary, a")) callDesk.focus();
  });
  byId("advanceNowButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/advance")); render(); }
    catch (error) { showToast(error.message, true); }
  });
}
