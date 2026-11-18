import { registerRenderer } from "../../core.js";
import { CRM_STATUS_KEYS, CRM_STATUS_LABELS, byId, setText } from "../../_core/format.js";
import { fieldText, locationText } from "../_prospects/query.js";
import { state } from "../../_core/state.js";
import { templateInfoPayload } from "./node-factory.js";

const PANEL_WIDTH_KEY = "godial-workflow-library-width";
const MIN_PANEL_W = 200;
const MAX_PANEL_W = 420;
const DEFAULT_PANEL_W = 272;

const FILTER_FIELDS = {
  business_type: { label: "Business type", kind: "text" },
  status: { label: "Status", kind: "status" },
  state: { label: "State", kind: "state" },
};

/** @type {Set<string>} */
let selectedLeadIds = new Set();
let sidebarBound = false;
let panelDrag = null;

function panelEl() {
  return document.getElementById("workflowCampaignCrm");
}

function listEl() {
  return document.getElementById("workflowCrmLeadList");
}

function filterField() {
  return document.getElementById("workflowCrmFilterField")?.value || "business_type";
}

function filterValueText() {
  const field = filterField();
  const config = FILTER_FIELDS[field];
  if (config?.kind === "status" || config?.kind === "state") {
    return (document.getElementById("workflowCrmFilterValueSelect")?.value || "").trim();
  }
  return (document.getElementById("workflowCrmFilterValueInput")?.value || "").trim();
}

function businessLabel(lead) {
  const business = String(lead?.business || "").trim();
  if (business) return business;
  const name = String(lead?.name || "").trim();
  return name || "Unnamed";
}

function leadMatchesFilter(lead) {
  const field = filterField();
  const value = filterValueText();
  if (!value) return true;
  const folded = value.toLocaleLowerCase();
  if (field === "business_type") {
    const raw = String(lead.business_type || fieldText(lead, "business type", "Business Type", "Industry") || "").trim();
    return raw.toLocaleLowerCase().includes(folded);
  }
  if (field === "status") {
    return (lead.status || "") === value;
  }
  if (field === "state") {
    return locationText(lead, "state").trim().toUpperCase() === value.toUpperCase();
  }
  return true;
}

function visibleLeads() {
  return state.leads.filter((lead) => lead?.id && leadMatchesFilter(lead));
}

function syncFilterValueControls() {
  const field = filterField();
  const config = FILTER_FIELDS[field] || FILTER_FIELDS.business_type;
  const select = document.getElementById("workflowCrmFilterValueSelect");
  const input = document.getElementById("workflowCrmFilterValueInput");
  const tag = document.getElementById("workflowCrmFilterActive");
  if (!select || !input) return;

  if (config.kind === "status") {
    select.hidden = false;
    input.hidden = true;
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All statuses";
    select.append(all);
    for (const key of CRM_STATUS_KEYS) {
      const option = document.createElement("option");
      option.value = key;
      option.textContent = CRM_STATUS_LABELS[key] || key;
      select.append(option);
    }
  } else if (config.kind === "state") {
    select.hidden = false;
    input.hidden = true;
    const states = [...new Set(state.leads.map((lead) => locationText(lead, "state")).filter(Boolean))];
    states.sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All states";
    select.append(all);
    for (const code of states) {
      const option = document.createElement("option");
      option.value = code;
      option.textContent = code;
      select.append(option);
    }
  } else {
    select.hidden = true;
    input.hidden = false;
    input.placeholder = "e.g. pest control";
  }

  const value = filterValueText();
  if (tag) {
    if (value) {
      tag.hidden = false;
      tag.textContent = `${config.label}: ${value}`;
    } else {
      tag.hidden = true;
      tag.textContent = "";
    }
  }
}

function updateSelectedSummary() {
  setText("workflowCrmSelectedCount", `Selected ${selectedLeadIds.size}`);
  const btn = document.getElementById("workflowCrmImportBtn");
  if (btn) btn.disabled = selectedLeadIds.size === 0;
}

function renderLeadList() {
  const list = listEl();
  if (!list) return;
  syncFilterValueControls();
  list.replaceChildren();
  const leads = visibleLeads();
  if (!leads.length) {
    const empty = document.createElement("p");
    empty.className = "workflow-crm-empty";
    empty.textContent = state.leads.length ? "No prospects match this filter." : "No prospects in CRM yet.";
    list.append(empty);
    updateSelectedSummary();
    return;
  }
  for (const lead of leads) {
    const row = document.createElement("div");
    row.className = "workflow-crm-lead-row";
    row.role = "listitem";
    row.dataset.leadId = lead.id;

    const label = document.createElement("label");
    label.className = "workflow-crm-lead-check";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedLeadIds.has(lead.id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) selectedLeadIds.add(lead.id);
      else selectedLeadIds.delete(lead.id);
      updateSelectedSummary();
    });
    label.append(checkbox);

    const body = document.createElement("div");
    body.className = "workflow-crm-lead-body";
    const name = document.createElement("span");
    name.className = "workflow-crm-lead-name";
    name.textContent = businessLabel(lead);
    const status = document.createElement("span");
    const statusKey = lead.status || "new";
    status.className = `workflow-crm-lead-status workflow-crm-lead-status--${statusKey}`;
    status.textContent = CRM_STATUS_LABELS[statusKey] || statusKey;
    body.append(name, status);

    row.append(label, body);
    list.append(row);
  }
  updateSelectedSummary();
}

function loadPanelWidth() {
  const el = panelEl();
  if (!el) return;
  try {
    const w = Number.parseInt(localStorage.getItem(PANEL_WIDTH_KEY) || "", 10);
    if (w >= MIN_PANEL_W && w <= MAX_PANEL_W) {
      el.style.setProperty("--workflow-library-width", `${w}px`);
    } else {
      el.style.setProperty("--workflow-library-width", `${DEFAULT_PANEL_W}px`);
    }
  } catch {
    el.style.setProperty("--workflow-library-width", `${DEFAULT_PANEL_W}px`);
  }
}

function savePanelWidth(width) {
  try {
    localStorage.setItem(PANEL_WIDTH_KEY, String(Math.round(width)));
  } catch {
    // ignore
  }
}

function onPanelResizeMove(event) {
  if (!panelDrag) return;
  const delta = event.clientX - panelDrag.originX;
  const next = Math.min(MAX_PANEL_W, Math.max(MIN_PANEL_W, panelDrag.originW + delta));
  panelEl()?.style.setProperty("--workflow-library-width", `${next}px`);
}

function endPanelResize() {
  if (!panelDrag) return;
  const w = panelEl()?.getBoundingClientRect().width;
  if (w) savePanelWidth(w);
  panelDrag = null;
  document.body.classList.remove("is-workflow-library-resizing");
  document.removeEventListener("pointermove", onPanelResizeMove);
  document.removeEventListener("pointerup", endPanelResize);
  document.removeEventListener("pointercancel", endPanelResize);
  window.dispatchEvent(new CustomEvent("godial-workflow-relayout"));
}

function startPanelResize(event) {
  const el = panelEl();
  if (!el || event.button !== 0) return;
  event.preventDefault();
  panelDrag = { originX: event.clientX, originW: el.getBoundingClientRect().width };
  document.body.classList.add("is-workflow-library-resizing");
  document.addEventListener("pointermove", onPanelResizeMove);
  document.addEventListener("pointerup", endPanelResize);
  document.addEventListener("pointercancel", endPanelResize);
}

function showNodeInfoDialog(templateId) {
  const dialog = document.getElementById("workflowNodeInfoDialog");
  const title = document.getElementById("workflowNodeInfoTitle");
  const body = document.getElementById("workflowNodeInfoBody");
  if (!dialog || !title || !body) return;
  const info = templateInfoPayload(templateId);
  if (!info) return;
  title.textContent = info.title;
  body.innerHTML = `
    <p class="workflow-info-meta"><strong>Lane:</strong> ${info.lane} · <strong>Type:</strong> ${info.type}</p>
    <p class="workflow-info-meta"><strong>Outputs:</strong> ${info.outputs}</p>
    <p class="workflow-info-meta"><strong>Shows:</strong> ${info.shows}</p>
    <p class="workflow-hint">${info.description}</p>
  `;
  if (typeof dialog.showModal === "function") dialog.showModal();
}

export function renderWorkflowCrmSidebar() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  renderLeadList();
}

export function bindWorkflowCrmSidebar() {
  if (sidebarBound) return;
  sidebarBound = true;
  loadPanelWidth();

  document.getElementById("workflowCrmFilterField")?.addEventListener("change", () => {
    document.getElementById("workflowCrmFilterValueSelect").value = "";
    document.getElementById("workflowCrmFilterValueInput").value = "";
    renderLeadList();
  });
  document.getElementById("workflowCrmFilterValueSelect")?.addEventListener("change", () => renderLeadList());
  document.getElementById("workflowCrmFilterValueInput")?.addEventListener("input", () => renderLeadList());
  document.getElementById("workflowCrmResizer")?.addEventListener("pointerdown", startPanelResize);
  document.getElementById("workflowCrmImportBtn")?.addEventListener("click", () => {
    if (selectedLeadIds.size) {
      // Step 3: import preview + membership records.
    }
  });

  document.getElementById("workflowNodeLayer")?.addEventListener("click", (event) => {
    const infoBtn = event.target.closest("[data-workflow-node-info]");
    if (!infoBtn) return;
    event.preventDefault();
    event.stopPropagation();
    showNodeInfoDialog(infoBtn.dataset.workflowNodeInfo);
  });

  registerRenderer(renderWorkflowCrmSidebar, "end", "workflow");
  renderWorkflowCrmSidebar();
}