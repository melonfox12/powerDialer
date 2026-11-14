import { registerRenderer } from "../../core.js";
import { state } from "../../_core/state.js";
import { agentsList, agentById } from "../_ai_dialer/agents.js";
import { openAgentCreateDialog } from "../_ai_dialer/agent-fleet-actions.js";
function notifyOfficeLayoutChanged() {
  window.dispatchEvent(new CustomEvent("godial-workflow-relayout"));
}

const OFFICE_KEY = "godial-workflow-office-seats";

/** @type {{ seatId: string, agentId: string }[]} */
let officeSeats = [];
let pendingCreateForOffice = false;
let officeBound = false;

function newSeatId() {
  return `seat-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
}

function loadOfficeSeats() {
  try {
    const saved = JSON.parse(localStorage.getItem(OFFICE_KEY) || "[]");
    if (Array.isArray(saved) && saved.length) {
      officeSeats = saved.filter((row) => row?.seatId && row?.agentId);
      return;
    }
  } catch {
  }
  officeSeats = agentsList().slice(0, 3).map((agent) => ({ seatId: newSeatId(), agentId: agent.id }));
  saveOfficeSeats();
}

function saveOfficeSeats() {
  try {
    localStorage.setItem(OFFICE_KEY, JSON.stringify(officeSeats));
  } catch {
  }
}

function seatStatus(agent) {
  if (!agent) return { label: "Missing", live: false };
  const live = Boolean(agent.primary && state.running);
  return { label: live ? "Live" : "Standby", live };
}

function openAgentSettingsDialog(agent) {
  const dialog = document.getElementById("workflowAgentSettingsDialog");
  const title = document.getElementById("workflowAgentDialogTitle");
  const nameInput = document.getElementById("workflowAgentDialogName");
  if (!dialog) return;
  const name = agent?.name || "Agent";
  const role = agent?.title ? ` — ${agent.title}` : "";
  if (title) title.textContent = `${name}${role} · desk settings`;
  if (nameInput) nameInput.value = name;
  dialog.showModal?.();
}

function renderImportList() {
  const list = document.getElementById("workflowOfficeImportList");
  if (!list) return;
  list.replaceChildren();
  const agents = agentsList();
  if (!agents.length) {
    const empty = document.createElement("p");
    empty.className = "workflow-hint";
    empty.textContent = "No agents yet. Use Create new agent on the previous step.";
    list.append(empty);
    return;
  }
  for (const agent of agents) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "workflow-office-import-row";
    row.dataset.agentId = agent.id;
    const name = document.createElement("strong");
    name.textContent = agent.name;
    const meta = document.createElement("span");
    meta.className = "workflow-office-import-meta";
    meta.textContent = agent.title || "AI dialer";
    row.append(name, meta);
    row.addEventListener("click", () => {
      addOfficeSeat(agent.id);
      document.getElementById("workflowAgentImportDialog")?.close();
      document.getElementById("workflowAgentAddDialog")?.close();
    });
    list.append(row);
  }
}

export function addOfficeSeat(agentId) {
  if (!agentId) return;
  officeSeats.push({ seatId: newSeatId(), agentId: String(agentId) });
  saveOfficeSeats();
  renderOfficeAgents();
  notifyOfficeLayoutChanged();
}

export function removeOfficeSeat(seatId) {
  officeSeats = officeSeats.filter((seat) => seat.seatId !== seatId);
  saveOfficeSeats();
  renderOfficeAgents();
  notifyOfficeLayoutChanged();
}

export function renderOfficeAgents() {
  const grid = document.getElementById("workflowOfficeGrid");
  if (!grid) return;
  grid.replaceChildren();
  if (!officeSeats.length) {
    const empty = document.createElement("p");
    empty.className = "workflow-hint workflow-office-empty";
    empty.textContent = "No agents in this office yet.";
    grid.append(empty);
    return;
  }
  for (const seat of officeSeats) {
    const agent = agentById(seat.agentId);
    const status = seatStatus(agent);
    const card = document.createElement("div");
    card.className = "workflow-agent-seat";
    card.role = "listitem";
    card.dataset.seatId = seat.seatId;
    card.dataset.agentId = seat.agentId;
    const head = document.createElement("div");
    head.className = "workflow-agent-seat-head";
    const titleWrap = document.createElement("div");
    titleWrap.className = "workflow-agent-seat-title";
    const name = document.createElement("strong");
    name.textContent = agent?.name || "Unknown agent";
    titleWrap.append(name);
    if (agent?.title) {
      const role = document.createElement("span");
      role.className = "workflow-agent-seat-role";
      role.textContent = agent.title;
      titleWrap.append(role);
    }
    const pill = document.createElement("span");
    pill.className = `workflow-agent-pill${status.live ? " is-live" : ""}`;
    pill.textContent = status.label;
    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "workflow-agent-seat-remove";
    remove.title = "Remove from office";
    remove.setAttribute("aria-label", `Remove ${agent?.name || "agent"} from office`);
    remove.textContent = "×";
    remove.addEventListener("pointerdown", (event) => event.stopPropagation());
    remove.addEventListener("click", () => removeOfficeSeat(seat.seatId));
    head.append(titleWrap, pill, remove);
    const body = document.createElement("div");
    body.className = "workflow-agent-seat-body";
    const meta = document.createElement("span");
    meta.className = "workflow-agent-meta";
    meta.innerHTML = agent?.primary
      ? "Live-line seat · Lines: <em>3</em>"
      : "Fleet seat · Lines: <em>3</em>";
    const actions = document.createElement("div");
    actions.className = "workflow-agent-seat-actions";
    const expand = document.createElement("button");
    expand.type = "button";
    expand.className = "button button-quiet workflow-agent-expand";
    expand.textContent = "Expand desk";
    expand.addEventListener("pointerdown", (event) => event.stopPropagation());
    expand.addEventListener("click", () => openAgentSettingsDialog(agent));
    actions.append(expand);
    body.append(meta, actions);
    card.append(head, body);
    grid.append(card);
  }
}

export function bindOfficeAgents() {
  if (officeBound) return;
  officeBound = true;
  loadOfficeSeats();
  renderOfficeAgents();

  const addDialog = document.getElementById("workflowAgentAddDialog");
  const importDialog = document.getElementById("workflowAgentImportDialog");

  document.getElementById("workflowOfficeAddAgent")?.addEventListener("pointerdown", (event) => event.stopPropagation());
  document.getElementById("workflowOfficeAddAgent")?.addEventListener("click", () => addDialog?.showModal());

  document.getElementById("workflowOfficeAddCancel")?.addEventListener("click", () => addDialog?.close());

  document.getElementById("workflowOfficeImportBtn")?.addEventListener("click", () => {
    renderImportList();
    importDialog?.showModal();
  });

  document.getElementById("workflowOfficeCreateBtn")?.addEventListener("click", () => {
    pendingCreateForOffice = true;
    addDialog?.close();
    openAgentCreateDialog();
  });

  importDialog?.addEventListener("click", (event) => {
    if (event.target === importDialog) importDialog.close();
  });

  addDialog?.addEventListener("click", (event) => {
    if (event.target === addDialog) addDialog.close();
  });

  window.addEventListener("godial-ai-agent-created", (event) => {
    if (!pendingCreateForOffice) return;
    pendingCreateForOffice = false;
    const agent = event.detail?.agent;
    if (agent?.id) addOfficeSeat(agent.id);
  });

  document.getElementById("aiDialerAgent-createDialog")?.addEventListener("close", () => {
    pendingCreateForOffice = false;
  });

  const settingsDialog = document.getElementById("workflowAgentSettingsDialog");
  settingsDialog?.addEventListener("click", (event) => {
    if (event.target === settingsDialog) settingsDialog.close();
  });

  registerRenderer(renderOfficeAgents, "end", "workflow");
}