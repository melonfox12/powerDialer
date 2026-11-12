import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson } from "../../_core/api.js";
import { showToast } from "../../_core/notify.js";
import { errorText } from "../../_core/notify.js";
import { render } from "../../core.js";
import { playbookExecutionReady } from "./playbook-editor.js";
import { paintSandboxVoiceChrome, startSandboxVoice, stopSandboxVoice } from "./sandbox-voice.js";

const DEFAULT_PROSPECT = { name: "Jordan", business: "Sample Services LLC" };

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

export function isSandboxActive() {
  const id = agentId();
  return Boolean(id && S.aiSandboxByAgent[id]?.active);
}

export function sandboxTranscript() {
  const box = session();
  if (!box) return [];
  const lines = box.transcript || [];
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
  box.partialProspect = "";
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
  paintSandboxVoiceChrome();
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
  stopSandboxVoice();
  box.active = true;
  box.ended = false;
  box.transcript = [];
  box.partialProspect = "";
  paintSandboxChrome();
  render();
  try {
    const [payload] = await Promise.all([
      postJson("/api/ai-agents/sandbox/start", { agent_id: id, prospect: DEFAULT_PROSPECT }),
      startSandboxVoice(id),
    ]);
    mergeSandboxPayload(payload);
    box.active = true;
    render();
    showToast("Sandbox live — speak as the prospect.");
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

  byId("aiDialerAgent-sandboxStartButton")?.addEventListener("click", () => {
    startSandbox().catch(() => {});
  });
  byId("aiDialerAgent-sandboxStopButton")?.addEventListener("click", () => {
    resetSandbox().catch(() => {});
  });
}
