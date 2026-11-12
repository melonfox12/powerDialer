import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson } from "../../_core/api.js";
import { showToast } from "../../_core/notify.js";
import { errorText } from "../../_core/notify.js";
import { render } from "../../core.js";

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
  return session()?.transcript || [];
}

function prospectPayload() {
  return {
    name: byId("aiDialerAgent-sandboxProspectName")?.value?.trim() || DEFAULT_PROSPECT.name,
    business: byId("aiDialerAgent-sandboxProspectBusiness")?.value?.trim() || DEFAULT_PROSPECT.business,
  };
}

function applyServerPayload(payload) {
  const box = session();
  if (!box) return;
  box.active = Boolean(payload.active);
  box.transcript = payload.transcript || [];
  box.ended = Boolean(payload.ended);
}

export function paintSandboxChrome() {
  const toggle = byId("aiDialerAgent-sandboxMode");
  const composer = byId("aiDialerAgent-sandboxComposer");
  const start = byId("aiDialerAgent-startButton");
  const stop = byId("aiDialerAgent-stopButton");
  const listen = byId("aiDialerAgent-listenInButton");
  const active = isSandboxActive();
  const id = agentId();
  const box = id ? S.aiSandboxByAgent[id] : null;

  if (toggle) {
    toggle.checked = active;
    toggle.disabled = Boolean(box?.busy) || (state.running && !active);
  }
  if (composer) {
    composer.hidden = !active;
    const input = byId("aiDialerAgent-sandboxInput");
    const send = byId("aiDialerAgent-sandboxSend");
    const ended = Boolean(box?.ended);
    if (input) input.disabled = box?.busy || ended;
    if (send) send.disabled = box?.busy || ended;
  }
  if (start) start.disabled = active || state.running || start.disabled;
  if (stop) stop.hidden = active ? true : stop.hidden;
  if (listen) listen.disabled = active || listen.disabled;

  const nameInput = byId("aiDialerAgent-sandboxProspectName");
  const bizInput = byId("aiDialerAgent-sandboxProspectBusiness");
  if (nameInput && !nameInput.value) nameInput.value = DEFAULT_PROSPECT.name;
  if (bizInput && !bizInput.value) bizInput.value = DEFAULT_PROSPECT.business;

  const viewport = document.querySelector("#aiDialerAgent-detailView .ai-live-viewport");
  viewport?.classList.toggle("is-sandbox", active);
}

async function startSandbox() {
  const id = agentId();
  if (!id) return;
  if (state.running) {
    showToast("Stop live dialing before sandbox mode.", true);
    paintSandboxChrome();
    return;
  }
  const box = session();
  box.busy = true;
  paintSandboxChrome();
  try {
    const payload = await postJson("/api/ai-agents/sandbox/start", {
      agent_id: id,
      prospect: prospectPayload(),
    });
    applyServerPayload(payload);
    showToast("Sandbox ready — you are the prospect.");
  } catch (error) {
    showToast(errorText(error, "Could not start sandbox."), true);
    box.active = false;
    byId("aiDialerAgent-sandboxMode").checked = false;
  } finally {
    box.busy = false;
    paintSandboxChrome();
    render();
  }
}

export async function resetSandbox() {
  const id = agentId();
  if (!id) return;
  const box = session();
  box.busy = true;
  paintSandboxChrome();
  try {
    await postJson("/api/ai-agents/sandbox/reset", { agent_id: id });
    box.active = false;
    box.transcript = [];
    box.ended = false;
    byId("aiDialerAgent-sandboxMode").checked = false;
    const input = byId("aiDialerAgent-sandboxInput");
    if (input) input.value = "";
  } catch (error) {
    showToast(errorText(error, "Could not reset sandbox."), true);
  } finally {
    box.busy = false;
    paintSandboxChrome();
    render();
  }
}

async function sendProspectLine() {
  const id = agentId();
  const input = byId("aiDialerAgent-sandboxInput");
  const text = input?.value?.trim() || "";
  if (!id || !text || !isSandboxActive()) return;
  const box = session();
  if (box.ended) return;
  box.busy = true;
  paintSandboxChrome();
  try {
    const payload = await postJson("/api/ai-agents/sandbox/turn", { agent_id: id, text });
    applyServerPayload(payload);
    input.value = "";
    if (payload.ended) showToast("Agent ended the call ([END_CALL]).");
  } catch (error) {
    showToast(errorText(error, "Agent could not reply."), true);
  } finally {
    box.busy = false;
    paintSandboxChrome();
    render();
  }
}

export function bindSandbox() {
  if (!S.aiSandboxByAgent) S.aiSandboxByAgent = {};

  byId("aiDialerAgent-sandboxMode")?.addEventListener("change", (event) => {
    if (event.target.checked) {
      startSandbox().catch(() => {});
    } else {
      resetSandbox().catch(() => {});
    }
  });

  byId("aiDialerAgent-sandboxComposer")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendProspectLine().catch(() => {});
  });

  byId("aiDialerAgent-sandboxRestart")?.addEventListener("click", () => {
    if (!isSandboxActive()) return;
    startSandbox().catch(() => {});
  });
}
