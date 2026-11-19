import { registerRenderer } from "../../_core/registry.js";
import { CRM_STATUS_LABELS, initials } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { leadNotes } from "../../_core/notes.js";
import { renderTranscriptEntries } from "../../_core/transcript.js";
import { pickerLeads } from "../../_core/sync-state.js";
import { workflowTemplateById } from "./node-catalog.js";
import { templateInfoPayload } from "./node-factory.js";
import { canvasEdgeLeadIds, nodeLeadCount, nodeLeadIds } from "./flow-snapshot.js";
import { clearWorkflowSelection, getWorkflowSelection, setWorkflowSelection } from "./selection.js";
import { buildAdjacentChainEdges } from "./transitions.js";

const VIEW_MODE_KEY = "godial-workflow-node-view-mode";

/** @type {"list" | "kanban"} */
let memberViewMode = "list";

function bodyEl() {
  return document.getElementById("workflowNodeViewBody");
}

function titleEl() {
  return document.getElementById("workflowNodeViewTitle");
}

function loadViewMode() {
  try {
    memberViewMode = localStorage.getItem(VIEW_MODE_KEY) === "kanban" ? "kanban" : "list";
  } catch {
    memberViewMode = "list";
  }
}

function saveViewMode() {
  try {
    localStorage.setItem(VIEW_MODE_KEY, memberViewMode);
  } catch {
    // ignore
  }
}

function leadMap() {
  const map = new Map();
  for (const lead of pickerLeads()) {
    if (lead?.id) map.set(lead.id, lead);
  }
  return map;
}

function leadsForIds(ids) {
  const map = leadMap();
  return (ids || []).map((id) => map.get(id)).filter(Boolean);
}

function businessLabel(lead) {
  return String(lead?.business || lead?.name || lead?.phone || "Unnamed").trim() || "Unnamed";
}

function statusLabel(status) {
  return CRM_STATUS_LABELS[status] || status || "—";
}

function buildViewToggle(activeMode) {
  const row = document.createElement("div");
  row.className = "workflow-inspector-toggle";
  row.setAttribute("role", "tablist");
  row.setAttribute("aria-label", "Member layout");
  for (const mode of ["list", "kanban"]) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = `workflow-inspector-toggle-btn${mode === activeMode ? " is-active" : ""}`;
    btn.setAttribute("role", "tab");
    btn.setAttribute("aria-selected", mode === activeMode ? "true" : "false");
    btn.dataset.memberView = mode;
    btn.textContent = mode === "list" ? "List" : "Kanban";
    btn.addEventListener("click", () => {
      memberViewMode = /** @type {"list" | "kanban"} */ (mode);
      saveViewMode();
      renderWorkflowNodeView();
    });
    row.append(btn);
  }
  return row;
}

function buildLeadRow(lead, onSelect) {
  const row = document.createElement("button");
  row.type = "button";
  row.className = "workflow-inspector-lead-row";
  row.innerHTML = `
    <span class="workflow-inspector-lead-avatar" aria-hidden="true">${initials(businessLabel(lead))}</span>
    <span class="workflow-inspector-lead-copy">
      <span class="workflow-inspector-lead-name">${businessLabel(lead)}</span>
      <span class="workflow-inspector-lead-meta">${formatPhoneNumber(lead.phone) || "—"} · ${statusLabel(lead.status)}</span>
    </span>
  `;
  row.addEventListener("click", (event) => {
    event.stopPropagation();
    onSelect(lead.id);
  });
  return row;
}

function buildLeadList(leadIds, via, contextId) {
  const leads = leadsForIds(leadIds);
  const wrap = document.createElement("div");
  wrap.className = "workflow-inspector-members";
  const heading = document.createElement("h4");
  heading.className = "workflow-inspector-section-title";
  heading.textContent = leads.length ? `Leads (${leads.length})` : "Leads";
  wrap.appendChild(heading);
  wrap.appendChild(buildViewToggle(memberViewMode));
  if (!leads.length) {
    const empty = document.createElement("p");
    empty.className = "workflow-node-view-empty";
    empty.textContent = "No leads at this step for the active campaign.";
    wrap.appendChild(empty);
    return wrap;
  }
  const onSelect = (leadId) => setWorkflowSelection({ type: "lead", leadId, via, contextId });
  if (memberViewMode === "list") {
    const list = document.createElement("div");
    list.className = "workflow-inspector-lead-list";
    list.setAttribute("role", "list");
    for (const lead of leads) {
      list.appendChild(buildLeadRow(lead, onSelect));
    }
    wrap.appendChild(list);
  } else {
    const board = document.createElement("div");
    board.className = "workflow-inspector-kanban";
    const columns = new Map();
    for (const lead of leads) {
      const key = lead.status || "unknown";
      if (!columns.has(key)) columns.set(key, []);
      columns.get(key).push(lead);
    }
    for (const [status, items] of columns) {
      const col = document.createElement("section");
      col.className = "workflow-inspector-kanban-col";
      col.innerHTML = `<h5 class="workflow-inspector-kanban-title">${statusLabel(status)} <span>${items.length}</span></h5>`;
      const stack = document.createElement("div");
      stack.className = "workflow-inspector-kanban-stack";
      for (const lead of items) {
        const card = document.createElement("button");
        card.type = "button";
        card.className = "workflow-inspector-kanban-card";
        card.textContent = businessLabel(lead);
        card.addEventListener("click", (event) => {
          event.stopPropagation();
          onSelect(lead.id);
        });
        stack.appendChild(card);
      }
      col.appendChild(stack);
      board.appendChild(col);
    }
    wrap.appendChild(board);
  }
  return wrap;
}

function buildNodeSettings(nodeId) {
  const template = workflowTemplateById(nodeId);
  const info = templateInfoPayload(nodeId);
  const wrap = document.createElement("div");
  wrap.className = "workflow-inspector-settings";
  const heading = document.createElement("h4");
  heading.className = "workflow-inspector-section-title";
  heading.textContent = info?.title || template?.title || nodeId;
  wrap.appendChild(heading);
  if (info?.description) {
    const desc = document.createElement("p");
    desc.className = "workflow-inspector-desc";
    desc.textContent = info.description;
    wrap.appendChild(desc);
  }
  const dl = document.createElement("dl");
  dl.className = "workflow-inspector-meta";
  const rows = [
    ["Type", info?.type || "—"],
    ["Lane", info?.lane || "—"],
    ["Outputs", info?.outputs || "—"],
    ["Shows", info?.shows || "—"],
    ["Leads here", String(nodeLeadCount(nodeId))],
    ["Per-node settings", "Campaign defaults (orchestrator pending)"],
  ];
  for (const [label, value] of rows) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  wrap.appendChild(dl);
  return wrap;
}

function buildInConversationSlots() {
  const wrap = document.createElement("div");
  wrap.className = "workflow-inspector-agents";
  wrap.innerHTML = `<h4 class="workflow-inspector-section-title">Agent slots</h4>`;
  const grid = document.createElement("div");
  grid.className = "workflow-inspector-agent-grid";
  for (let seat = 1; seat <= 8; seat += 1) {
    const slot = document.createElement("div");
    slot.className = `workflow-inspector-agent-slot${seat <= 2 ? " is-live" : ""}`;
    slot.innerHTML = `
      <span class="workflow-inspector-agent-seat">Seat ${seat}</span>
      <span class="workflow-inspector-agent-state">${seat <= 2 ? "Live" : "Idle"}</span>
      <span class="workflow-inspector-agent-preview">${seat <= 2 ? "Transcript preview…" : "—"}</span>
    `;
    grid.appendChild(slot);
  }
  wrap.appendChild(grid);
  return wrap;
}

function buildLeadRecord(leadId) {
  const lead = leadMap().get(leadId);
  const sel = getWorkflowSelection();
  const wrap = document.createElement("div");
  wrap.className = "workflow-inspector-lead-record";
  const back = document.createElement("button");
  back.type = "button";
  back.className = "button button-quiet workflow-inspector-back";
  back.textContent = "← Back to list";
  back.addEventListener("click", () => {
    if (sel?.type !== "lead") {
      clearWorkflowSelection();
      return;
    }
    if (sel.via === "node") {
      setWorkflowSelection({ type: "node", nodeId: sel.contextId });
      return;
    }
    const edge = buildAdjacentChainEdges().find((row) => row.id === sel.contextId);
    if (edge) {
      setWorkflowSelection({ type: "edge", edgeId: edge.id, from: edge.from, to: edge.to });
      return;
    }
    clearWorkflowSelection();
  });
  wrap.appendChild(back);
  if (!lead) {
    const miss = document.createElement("p");
    miss.className = "workflow-node-view-empty";
    miss.textContent = "Lead details are not in the current CRM catalog. Open Global CRM or refresh.";
    wrap.appendChild(miss);
    return wrap;
  }
  const title = document.createElement("h4");
  title.className = "workflow-inspector-section-title";
  title.textContent = businessLabel(lead);
  wrap.appendChild(title);
  const dl = document.createElement("dl");
  dl.className = "workflow-inspector-meta";
  const pairs = [
    ["Contact", lead.name || "—"],
    ["Phone", formatPhoneNumber(lead.phone) || "—"],
    ["Business", lead.business || "—"],
    ["Status", statusLabel(lead.status)],
    ["Timezone", lead.timezone || "—"],
  ];
  for (const [label, value] of pairs) {
    const dt = document.createElement("dt");
    dt.textContent = label;
    const dd = document.createElement("dd");
    dd.textContent = value;
    dl.appendChild(dt);
    dl.appendChild(dd);
  }
  wrap.appendChild(dl);
  const notesHeading = document.createElement("h5");
  notesHeading.className = "workflow-inspector-subtitle";
  notesHeading.textContent = "Notes";
  wrap.appendChild(notesHeading);
  const notes = document.createElement("p");
  notes.className = "workflow-inspector-notes";
  notes.textContent = leadNotes(lead) || "No notes yet.";
  wrap.appendChild(notes);
  const transcriptHeading = document.createElement("h5");
  transcriptHeading.className = "workflow-inspector-subtitle";
  transcriptHeading.textContent = "Transcript";
  wrap.appendChild(transcriptHeading);
  const transcriptBox = document.createElement("div");
  transcriptBox.className = "workflow-inspector-transcript";
  renderTranscriptEntries(transcriptBox, (lead.transcript || []).slice(-6), "No transcript yet.");
  wrap.appendChild(transcriptBox);
  const histHeading = document.createElement("h5");
  histHeading.className = "workflow-inspector-subtitle";
  histHeading.textContent = "Status history";
  wrap.appendChild(histHeading);
  const history = document.createElement("ul");
  history.className = "workflow-inspector-history";
  const entries = (lead.status_history || []).slice(-8).reverse();
  if (!entries.length) {
    history.innerHTML = `<li class="workflow-node-view-empty">No history recorded.</li>`;
  } else {
    for (const row of entries) {
      const li = document.createElement("li");
      li.textContent = `${statusLabel(row.from_status)} → ${statusLabel(row.to_status)}`;
      history.appendChild(li);
    }
  }
  wrap.appendChild(history);
  return wrap;
}

function paintSelectionChrome() {
  for (const node of document.querySelectorAll("[data-workflow-node]")) {
    const id = node.dataset.workflowTemplate;
    const sel = getWorkflowSelection();
    const on = sel?.type === "node" && sel.nodeId === id;
    node.classList.toggle("is-workflow-selected", on);
  }
  for (const path of document.querySelectorAll("[data-workflow-edge]")) {
    const id = path.getAttribute("data-workflow-edge");
    const sel = getWorkflowSelection();
    const on = sel?.type === "edge" && sel.edgeId === id;
    path.classList.toggle("is-workflow-edge-selected", on);
  }
}

export function renderWorkflowNodeView() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  const view = document.getElementById("workflowViewport");
  if (view?.classList.contains("is-workflow-interacting") || view?.classList.contains("is-panning")) return;
  const body = bodyEl();
  const title = titleEl();
  if (!body || !title) return;
  const sel = getWorkflowSelection();
  paintSelectionChrome();
  body.replaceChildren();
  if (!sel) {
    title.textContent = "Node view";
    const empty = document.createElement("p");
    empty.className = "workflow-node-view-empty";
    empty.textContent = "Select a node, edge, or lead on the canvas to inspect it here.";
    body.appendChild(empty);
    return;
  }
  if (sel.type === "lead") {
    title.textContent = "Lead record";
    body.appendChild(buildLeadRecord(sel.leadId));
    return;
  }
  if (sel.type === "node") {
    const template = workflowTemplateById(sel.nodeId);
    title.textContent = template?.title || sel.nodeId;
    body.appendChild(buildNodeSettings(sel.nodeId));
    if (sel.nodeId === "in-conversation") {
      body.appendChild(buildInConversationSlots());
    }
    body.appendChild(buildLeadList(nodeLeadIds(sel.nodeId), "node", sel.nodeId));
    return;
  }
  if (sel.type === "edge") {
    const fromT = workflowTemplateById(sel.from);
    const toT = workflowTemplateById(sel.to);
    title.textContent = `${fromT?.title || sel.from} → ${toT?.title || sel.to}`;
    const meta = document.createElement("p");
    meta.className = "workflow-inspector-desc";
    meta.textContent = "Leads counted on this hop for the active campaign.";
    body.appendChild(meta);
    const edge = { id: sel.edgeId, from: sel.from, to: sel.to };
    body.appendChild(buildLeadList(canvasEdgeLeadIds(edge), "edge", sel.edgeId));
  }
}

export function bindWorkflowNodeView() {
  loadViewMode();
  registerRenderer(renderWorkflowNodeView, "end", "workflow");
  window.addEventListener("godial-workflow-selection", renderWorkflowNodeView);
  window.addEventListener("godial-workflow-flow", renderWorkflowNodeView);
}

export function selectWorkflowNode(nodeId) {
  if (!nodeId) return;
  setWorkflowSelection({ type: "node", nodeId });
}

export function selectWorkflowEdge(edgeId, from, to) {
  if (!edgeId) return;
  setWorkflowSelection({ type: "edge", edgeId, from, to });
}