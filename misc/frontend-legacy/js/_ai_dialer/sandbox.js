import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson } from "../../_core/api.js";
import { showToast } from "../../_core/notify.js";
import { errorText } from "../../_core/notify.js";
import { render } from "../../core.js";
import { playbookExecutionReady } from "./playbook-editor.js";
import {
  paintSandboxVoiceChrome,
  isSandboxAgentSpeaking,
  pauseSandboxCapture,
  resumeSandboxCapture,
  beginSandboxPolling,
  ensureSandboxPlayback,
  ensureSandboxPlaybackReady,
  playSandboxOutboundChunks,
  prepareSandboxTextSession,
  prepareSandboxVoiceSession,
  stopSandboxVoice,
  syncSandboxVoiceTranscriptSeq,
  waitForSandboxOpening,
} from "./sandbox-voice.js";

const DEFAULT_PROSPECT = { name: "Jordan", business: "Sample Services LLC" };
const SANDBOX_MODE_KEY = "ai-sandbox-interaction-mode";

function agentId() {
  return S.aiDialerSelectedAgentId;
}

function session() {
  const id = agentId();
  if (!id) return null;
  if (!S.aiSandboxByAgent[id]) {
    S.aiSandboxByAgent[id] = { active: false, transcript: [], ended: false, busy: false };
  }
  return S.aiSandboxByAgent[id];
}

function readSandboxModeFromUi() {
  const checked = document.querySelector('input[name="aiDialerAgent-sandboxMode"]:checked');
  const mode = checked?.value === "text" ? "text" : "voice";
  return mode;
}

function syncSandboxModeToUi(mode) {
  const voice = byId("aiDialerAgent-sandboxModeVoice");
  const text = byId("aiDialerAgent-sandboxModeText");
  if (mode === "text" && text) text.checked = true;
  else if (voice) voice.checked = true;
}

export function isSandboxActive() {
  const id = agentId();
  return Boolean(id && S.aiSandboxByAgent[id]?.active);
}

export function isSandboxVoiceMode() {
  const box = session();
  if (box?.active) return box.interactionMode !== "text";
  const saved = localStorage.getItem(SANDBOX_MODE_KEY);
  if (saved === "text" || saved === "voice") return saved === "voice";
  return readSandboxModeFromUi() === "voice";
}

export function sandboxTranscript() {
  const box = session();
  if (!box) return [];
  const lines = box.transcript || [];
  if (!isSandboxVoiceMode()) return lines;
  const partial = String(box.partialProspect || "").trim();
  if (!partial) return lines;
  return [
    ...lines,
    {
      id: "sandbox-prospect-partial",
      speaker: "Prospect",
      text: partial,
      partial: true,
      timestamp: new Date().toISOString(),
    },
  ];
}

export function mergeSandboxPayload(payload) {
  const box = session();
  if (!box) return;
  box.active = Boolean(payload.active);
  box.transcript = payload.transcript || [];
  box.ended = Boolean(payload.ended);
  box.transcript_seq = payload.transcript_seq || 0;
  box.reply_busy = Boolean(payload.reply_busy);
  box.booting = Boolean(payload.booting);
  box.tts_busy = Boolean(payload.tts_busy);
  if (payload.audio_encoding) box.audio_encoding = payload.audio_encoding;
  if (payload.audio_sample_rate) box.audio_sample_rate = payload.audio_sample_rate;
  box.partialProspect = "";
}

/** @returns {Promise<object|null>} sandbox payload when the agent replied */
export async function sendSandboxProspectMessage(text) {
  const id = agentId();
  const line = String(text || "").trim();
  if (!id || !line || !isSandboxActive()) return null;
  const box = session();
  if (box.ended || box.reply_busy) return null;
  box.reply_busy = true;
  box.partialProspect = "";
  render();
  try {
    const payload = await postJson("/api/ai-agents/sandbox/turn", { agent_id: id, text: line });
    mergeSandboxPayload(payload);
    syncSandboxVoiceTranscriptSeq(payload.transcript_seq);
    if (payload.chunks?.length) {
      playSandboxOutboundChunks(payload.chunks);
    }
    if (payload.ended) showToast("Agent ended the call ([END_CALL]).");
    render();
    return payload;
  } catch (error) {
    showToast(errorText(error, "Agent could not reply."), true);
    box.reply_busy = false;
    render();
    return null;
  }
}

function paintSandboxComposer() {
  const box = session();
  const active = isSandboxActive();
  const canType = active && !box?.ended;
  const composer = byId("aiDialerAgent-sandboxComposer");
  const input = byId("aiDialerAgent-sandboxInput");
  const send = byId("aiDialerAgent-sandboxSend");
  const hint = byId("aiDialerAgent-sandboxComposerHint");
  if (composer) composer.hidden = !canType;
  const disabled = !canType || Boolean(box?.reply_busy);
  if (input) input.disabled = disabled;
  if (send) send.disabled = disabled;
  if (hint) {
    hint.textContent = isSandboxVoiceMode()
      ? "You are the prospect — type a line or use your mic."
      : "You are the prospect — message only (no mic). You still hear the agent in your headphones.";
  }
}

function paintSandboxModeChrome() {
  const active = isSandboxActive();
  const box = session();
  const modeLocked = active && !box?.ended;
  const fieldset = byId("aiDialerAgent-sandboxModeFieldset");
  if (fieldset) {
    fieldset.disabled = modeLocked;
    fieldset.setAttribute("aria-disabled", modeLocked ? "true" : "false");
  }
  if (!modeLocked && box?.interactionMode) syncSandboxModeToUi(box.interactionMode);

  const voiceUi = isSandboxVoiceMode();
  const audioTest = byId("aiDialerAgent-sandboxAudioTest");
  const waveRail = byId("aiDialerAgent-sandboxWaveformRail");
  if (audioTest) audioTest.hidden = !voiceUi;
  if (waveRail) waveRail.hidden = !voiceUi;
}

export function paintSandboxChrome() {
  const active = isSandboxActive();
  const id = agentId();
  const box = id ? S.aiSandboxByAgent[id] : null;
  const sandboxStart = byId("aiDialerAgent-sandboxStartButton");
  const sandboxStop = byId("aiDialerAgent-sandboxStopButton");
  const deskStart = byId("aiDialerAgent-startButton");
  const deskStop = byId("aiDialerAgent-stopButton");
  const listen = byId("aiDialerAgent-listenInButton");

  if (sandboxStart) {
    sandboxStart.disabled = state.running || (active && !box?.ended);
    sandboxStart.hidden = Boolean(active && !box?.ended);
  }
  if (sandboxStop) {
    sandboxStop.hidden = !active;
    sandboxStop.disabled = !active;
  }
  if (active) {
    if (deskStart) deskStart.disabled = true;
    if (deskStop) deskStop.hidden = true;
    if (listen) listen.disabled = true;
  }
  paintSandboxModeChrome();
  paintSandboxComposer();
  paintSandboxVoiceChrome();
}

async function submitSandboxCompose() {
  const input = byId("aiDialerAgent-sandboxInput");
  if (!input) return;
  const text = input.value.trim();
  if (!text) return;
  if (isSandboxVoiceMode()) pauseSandboxCapture();
  const payload = await sendSandboxProspectMessage(text);
  if (payload) input.value = "";
  const box = session();
  if (
    isSandboxVoiceMode()
    && box
    && !box.ended
    && !box.reply_busy
    && !isSandboxAgentSpeaking()
  ) {
    resumeSandboxCapture();
  }
  paintSandboxComposer();
}

async function startSandbox() {
  const id = agentId();
  if (!id) return;
  if (!playbookExecutionReady(id)) {
    showToast("Save the prompt first so instructions are compiled for this seat.", true);
    paintSandboxChrome();
    return;
  }
  if (state.running) {
    showToast("Stop live dialing before using the sandbox.", true);
    paintSandboxChrome();
    return;
  }
  const box = session();
  if (box.active && !box.ended) return;
  const interactionMode = readSandboxModeFromUi();
  localStorage.setItem(SANDBOX_MODE_KEY, interactionMode);
  box.interactionMode = interactionMode;
  stopSandboxVoice();
  box.active = true;
  box.ended = false;
  box.transcript = [];
  box.partialProspect = "";
  paintSandboxChrome();
  render();
  try {
    if (interactionMode === "text") {
      await prepareSandboxTextSession(id);
    } else {
      await prepareSandboxVoiceSession(id);
    }
    const payload = await postJson("/api/ai-agents/sandbox/start", {
      agent_id: id,
      prospect: DEFAULT_PROSPECT,
    });
    await ensureSandboxPlaybackReady({ force: true });
    await postJson("/api/ai-agents/sandbox/playback-ready", { agent_id: id });
    mergeSandboxPayload(payload);
    box.active = true;
    beginSandboxPolling(id);
    render();
    await waitForSandboxOpening(id);
    render();
    showToast(
      interactionMode === "text"
        ? "Text sandbox live — send messages as the prospect."
        : "Voice sandbox live — speak or type as the prospect.",
    );
  } catch (error) {
    showToast(errorText(error, "Could not start sandbox."), true);
    box.active = false;
    stopSandboxVoice();
  } finally {
    paintSandboxChrome();
    render();
  }
}

export async function resetSandbox() {
  const id = agentId();
  if (!id) return;
  const box = session();
  stopSandboxVoice();
  box.active = false;
  box.ended = false;
  box.transcript = [];
  box.transcript_seq = 0;
  box.partialProspect = "";
  box.reply_busy = false;
  const input = byId("aiDialerAgent-sandboxInput");
  if (input) input.value = "";
  paintSandboxChrome();
  render();
  try {
    await postJson("/api/ai-agents/sandbox/reset", { agent_id: id });
  } catch (error) {
    showToast(errorText(error, "Could not stop sandbox."), true);
  } finally {
    paintSandboxChrome();
    render();
  }
}

export function bindSandbox() {
  if (!S.aiSandboxByAgent) S.aiSandboxByAgent = {};

  const saved = localStorage.getItem(SANDBOX_MODE_KEY);
  if (saved === "text" || saved === "voice") syncSandboxModeToUi(saved);

  for (const input of document.querySelectorAll('input[name="aiDialerAgent-sandboxMode"]')) {
    input.addEventListener("change", () => {
      if (isSandboxActive()) return;
      localStorage.setItem(SANDBOX_MODE_KEY, readSandboxModeFromUi());
      paintSandboxChrome();
    });
  }

  byId("aiDialerAgent-sandboxStartButton")?.addEventListener("click", () => {
    startSandbox().catch(() => {});
  });
  byId("aiDialerAgent-sandboxStopButton")?.addEventListener("click", () => {
    resetSandbox().catch(() => {});
  });
  byId("aiDialerAgent-sandboxComposer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    submitSandboxCompose().catch(() => {});
  });
  byId("aiDialerAgent-sandboxInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submitSandboxCompose().catch(() => {});
    }
  });

  paintSandboxChrome();
}
