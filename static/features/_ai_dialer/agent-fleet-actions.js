import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson } from "../../_core/api.js";
import { showToast } from "../../_core/notify.js";
import { errorText } from "../../_core/notify.js";
import { render } from "../../core.js";
import { loadAppState } from "../../_core/sync-state.js";
import { resetWorkspaceTabs, paintWorkspaceTabs } from "./workspace-tabs.js";
import { ensurePlaybookLoaded } from "./playbook-editor.js";
import { invalidateFleetGrid, syncAiDialerViews } from "./fleet.js";

function mergeAiAgentsView(payload) {
  if (payload?.ai_agents) state.ai_agents = payload.ai_agents;
}

export async function createAgentSeat(name, title) {
  const payload = await postJson("/api/ai-agents/create", {
    name: String(name || "").trim(),
    title: String(title || "").trim() || undefined,
  });
  mergeAiAgentsView(payload);
  await loadAppState().catch(() => {});
  invalidateFleetGrid();
  const agent = payload.agent;
  if (agent?.id) {
    S.aiDialerSelectedAgentId = agent.id;
    resetWorkspaceTabs();
    paintWorkspaceTabs();
    ensurePlaybookLoaded(agent.id).catch(() => {});
    syncAiDialerViews();
  }
  render();
  return agent;
}

export async function duplicateAgentSeat(sourceAgentId, name) {
  const payload = await postJson("/api/ai-agents/duplicate", {
    source_agent_id: sourceAgentId,
    name: name ? String(name).trim() : undefined,
  });
  mergeAiAgentsView(payload);
  await loadAppState().catch(() => {});
  invalidateFleetGrid();
  const agent = payload.agent;
  if (agent?.id) {
    S.aiDialerSelectedAgentId = agent.id;
    resetWorkspaceTabs();
    paintWorkspaceTabs();
    ensurePlaybookLoaded(agent.id).catch(() => {});
    syncAiDialerViews();
  }
  render();
  showToast(agent?.name ? `Duplicated as ${agent.name}.` : "Agent duplicated.");
  return agent;
}

export async function deleteAgentSeat(agentId) {
  const payload = await postJson("/api/ai-agents/delete", { agent_id: agentId });
  mergeAiAgentsView(payload);
  await loadAppState().catch(() => {});
  invalidateFleetGrid();
  if (S.aiDialerSelectedAgentId === agentId) {
    S.aiDialerSelectedAgentId = null;
    resetWorkspaceTabs();
  }
  syncAiDialerViews();
  render();
  showToast("Agent seat deleted.");
}

function openCreateDialog() {
  const dialog = byId("aiDialerAgent-createDialog");
  const nameInput = byId("aiDialerAgent-createName");
  const titleInput = byId("aiDialerAgent-createTitle");
  if (!dialog || !nameInput) return;
  nameInput.value = "";
  if (titleInput) titleInput.value = "";
  dialog.showModal();
  nameInput.focus();
}

export function bindAgentFleetActions() {
  byId("aiDialerAgent-newAgentButton")?.addEventListener("click", () => openCreateDialog());

  const form = byId("aiDialerAgent-createForm");
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = byId("aiDialerAgent-createName")?.value?.trim();
    const title = byId("aiDialerAgent-createTitle")?.value?.trim();
    if (!name) {
      showToast("Enter a name for the agent.", true);
      return;
    }
    const submit = form.querySelector("[type=submit]");
    if (submit) submit.disabled = true;
    try {
      await createAgentSeat(name, title);
      byId("aiDialerAgent-createDialog")?.close();
      showToast(`Created ${name}.`);
    } catch (error) {
      showToast(errorText(error, "Could not create agent."), true);
    } finally {
      if (submit) submit.disabled = false;
    }
  });

  byId("aiDialerAgent-createCancel")?.addEventListener("click", () => {
    byId("aiDialerAgent-createDialog")?.close();
  });

  byId("aiDialerAgent-detailDuplicate")?.addEventListener("click", () => {
    const agentId = S.aiDialerSelectedAgentId;
    if (!agentId) return;
    duplicateAgentSeat(agentId).catch((error) => {
      showToast(errorText(error, "Could not duplicate agent."), true);
    });
  });

  byId("aiDialerAgent-detailDelete")?.addEventListener("click", () => {
    const agentId = S.aiDialerSelectedAgentId;
    if (!agentId) return;
    if (!window.confirm("Delete this agent seat? Its prompt is removed and any pool is released.")) return;
    deleteAgentSeat(agentId).catch((error) => {
      showToast(errorText(error, "Could not delete agent."), true);
    });
  });
}

export async function duplicateAgentFromFleet(agentId, event) {
  event?.stopPropagation?.();
  event?.preventDefault?.();
  try {
    await duplicateAgentSeat(agentId);
  } catch (error) {
    showToast(errorText(error, "Could not duplicate agent."), true);
  }
}

export async function deleteAgentFromFleet(agentId, event) {
  event?.stopPropagation?.();
  event?.preventDefault?.();
  if (!window.confirm("Delete this agent seat?")) return;
  try {
    await deleteAgentSeat(agentId);
  } catch (error) {
    showToast(errorText(error, "Could not delete agent."), true);
  }
}
