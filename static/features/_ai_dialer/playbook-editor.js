import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson, request } from "../../_core/api.js";
import { errorText } from "../../_core/notify.js";
import { agentById } from "./agents.js";
import { openPlaybookTab, paintWorkspaceTabs } from "./workspace-tabs.js";

const saveTimers = new Map();

function playbookCacheKey(agentId) {
  return String(agentId || "");
}

export function playbookForAgent(agentId) {
  return S.aiPlaybookByAgent?.[playbookCacheKey(agentId)] || null;
}

function setPlaybookCache(agentId, playbook) {
  if (!S.aiPlaybookByAgent) S.aiPlaybookByAgent = {};
  S.aiPlaybookByAgent[playbookCacheKey(agentId)] = playbook;
}

function promptFields() {
  return [byId("aiDialerAgent-playbookPrompt"), byId("aiDialerAgent-playbookPromptWidget")].filter(Boolean);
}

export function readPlaybookPrompt() {
  const field = byId("aiDialerAgent-playbookPrompt") || byId("aiDialerAgent-playbookPromptWidget");
  return field?.value ?? "";
}

function syncPromptFields(text, source) {
  for (const field of promptFields()) {
    if (field === source) continue;
    if (field.value !== text) field.value = text;
  }
}

export async function loadPlaybook(agentId) {
  const id = String(agentId || "").trim();
  if (!id) return null;
  if (playbookForAgent(id)) return playbookForAgent(id);
  try {
    const payload = await request(`/api/ai-agents/playbook?agent_id=${encodeURIComponent(id)}`);
    setPlaybookCache(id, payload.playbook);
    return payload.playbook;
  } catch (error) {
    console.warn("playbook load", errorText(error, ""));
    return null;
  }
}

export function fillPlaybookForm(playbook) {
  const text = playbook?.prompt ?? "";
  syncPromptFields(text, null);
}

export function renderPlaybookPreview() {
  const text = readPlaybookPrompt() || playbookForAgent(S.aiDialerSelectedAgentId)?.prompt || "";
  const widget = byId("aiDialerAgent-playbookPromptWidget");
  if (widget && document.activeElement !== widget) {
    if (widget.value !== text) widget.value = text;
  }
}

export function schedulePlaybookSave(agentId) {
  const id = String(agentId || S.aiDialerSelectedAgentId || "").trim();
  if (!id) return;
  const status = byId("aiDialerAgent-playbookSaveStatus");
  if (status) status.textContent = "Saving…";
  clearTimeout(saveTimers.get(id));
  saveTimers.set(
    id,
    setTimeout(() => {
      persistPlaybook(id).catch(() => {});
    }, 650),
  );
}

async function persistPlaybook(agentId) {
  const status = byId("aiDialerAgent-playbookSaveStatus");
  const prompt = readPlaybookPrompt();
  try {
    const payload = await postJson("/api/ai-agents/playbook", { agent_id: agentId, playbook: { prompt } });
    setPlaybookCache(agentId, payload.playbook);
    fillPlaybookForm(payload.playbook);
    if (status) status.textContent = "Saved";
    setTimeout(() => {
      if (status?.textContent === "Saved") status.textContent = "";
    }, 1800);
  } catch (error) {
    if (status) status.textContent = errorText(error, "Could not save.");
  }
}

export async function ensurePlaybookLoaded(agentId) {
  const agent = agentById(agentId);
  let playbook = playbookForAgent(agentId);
  if (!playbook) playbook = await loadPlaybook(agentId);
  if (!playbook && agent) {
    playbook = { prompt: "" };
  }
  if (playbook) {
    setPlaybookCache(agentId, playbook);
    fillPlaybookForm(playbook);
  }
}

function onPromptInput(event) {
  const agentId = S.aiDialerSelectedAgentId;
  if (!agentId) return;
  const text = event.target.value;
  syncPromptFields(text, event.target);
  setPlaybookCache(agentId, { ...(playbookForAgent(agentId) || {}), prompt: text });
  schedulePlaybookSave(agentId);
}

export function bindPlaybookEditor() {
  for (const field of promptFields()) {
    field.addEventListener("input", onPromptInput);
  }
  byId("aiDialerAgent-expandPlaybookTab")?.addEventListener("click", () => {
    openPlaybookTab();
    paintWorkspaceTabs();
    byId("aiDialerAgent-playbookPrompt")?.focus();
  });
}
