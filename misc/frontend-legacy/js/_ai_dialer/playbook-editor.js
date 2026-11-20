import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson, request } from "../../_core/api.js";
import { errorText } from "../../_core/notify.js";
import { agentById } from "./agents.js";

const saveTimers = new Map();

function playbookCacheKey(agentId) {
  return String(agentId || "");
}

export function playbookForAgent(agentId) {
  return S.aiPlaybookByAgent?.[playbookCacheKey(agentId)] || null;
}

export function playbookExecutionReady(agentId) {
  const book = playbookForAgent(agentId);
  if (!book) return false;
  if (book.execution_ready === false) return false;
  return Boolean(book.compiled?.system_prompt?.trim());
}

function setPlaybookCache(agentId, playbook) {
  if (!S.aiPlaybookByAgent) S.aiPlaybookByAgent = {};
  S.aiPlaybookByAgent[playbookCacheKey(agentId)] = playbook;
}

export function readPlaybookPrompt() {
  return byId("aiDialerAgent-playbookPrompt")?.value ?? "";
}

function formatCompiledAt(iso) {
  if (!iso) return "";
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return "";
  }
}

export function paintPlaybookCompileState(agentId = S.aiDialerSelectedAgentId) {
  const id = String(agentId || "").trim();
  if (!id) return;
  const book = playbookForAgent(id);
  const ready = playbookExecutionReady(id);
  const saveStatus = byId("aiDialerAgent-playbookSaveStatus");
  const bakedDetails = byId("aiDialerAgent-playbookBakedDetails");
  const preview = byId("aiDialerAgent-playbookCompiledPreview");
  const compiledAt = formatCompiledAt(book?.compiled?.compiled_at);
  if (saveStatus && saveStatus.textContent !== "Saving…" && saveStatus.textContent !== "Saved") {
    if (ready && compiledAt) saveStatus.textContent = `Compiled ${compiledAt} · ready to run`;
    else if (book && !ready) saveStatus.textContent = "Save to compile instructions for this seat";
    else if (!saveStatus.textContent) saveStatus.textContent = "";
  }
  const baked = book?.compiled?.system_prompt?.trim() || "";
  if (preview) preview.textContent = baked;
  if (bakedDetails) bakedDetails.hidden = !baked;
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
  const field = byId("aiDialerAgent-playbookPrompt");
  if (field && field.value !== (playbook?.prompt ?? "")) {
    field.value = playbook?.prompt ?? "";
  }
  paintPlaybookCompileState();
}

export function renderPlaybookPreview() {
  if (S.dashboardTab !== "aiDialerAgent" || !S.aiDialerSelectedAgentId) return;
  paintPlaybookCompileState();
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
    paintPlaybookCompileState(agentId);
    setTimeout(() => {
      paintPlaybookCompileState(agentId);
    }, 100);
    setTimeout(() => {
      if (status?.textContent === "Saved") status.textContent = "";
      paintPlaybookCompileState(agentId);
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
    playbook = { prompt: "", execution_ready: false };
  }
  if (playbook) {
    setPlaybookCache(agentId, playbook);
    fillPlaybookForm(playbook);
  }
}

function onPromptInput() {
  const agentId = S.aiDialerSelectedAgentId;
  if (!agentId) return;
  const text = readPlaybookPrompt();
  setPlaybookCache(agentId, {
    ...(playbookForAgent(agentId) || {}),
    prompt: text,
    execution_ready: false,
  });
  paintPlaybookCompileState(agentId);
  schedulePlaybookSave(agentId);
}

export function bindPlaybookEditor() {
  byId("aiDialerAgent-playbookPrompt")?.addEventListener("input", onPromptInput);
}
