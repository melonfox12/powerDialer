import { registerRenderer } from "../../_core/registry.js";
import { CRM_STATUS_KEYS, CRM_STATUS_LABELS, setText } from "../../_core/format.js";
import { fieldText, locationText } from "../_prospects/query.js";
import { pickerLeads } from "../../_core/sync-state.js";
import { state } from "../../_core/state.js";
import { templateInfoPayload } from "./node-factory.js";

const PANEL_WIDTH_KEY = "godial-workflow-library-width";
const MIN_PANEL_W = 200;
const MAX_PANEL_W = 420;
const DEFAULT_PANEL_W = 272;
const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 220;

const FILTER_FIELDS = {
  business_type: { label: "Business type", kind: "text" },
  status: { label: "Status", kind: "status" },
  state: { label: "State", kind: "state" },
};

/** @type {Set<string>} */
let selectedLeadIds = new Set();
let selectAllMatching = false;
let sidebarBound = false;
let panelDrag = null;
let lastListSignature = "";
let lastFilterUiSignature = "";
let visibleCount = PAGE_SIZE;
let searchQuery = "";
let searchDebounceTimer = null;
/** @type {{ key: string, ids: string[] } | null} */
let matchingIdCache = null;
let stateOptionsCache = { version: -1, states: [] };

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

function leadStateText(lead) {
  const direct = String(lead?.state || "").trim();
  if (direct) return direct;
  return locationText(lead, "state");
}

function leadMatchesFilter(lead) {
  const field = filterField();
  const value = filterValueText();
  if (!value) return true;
  const folded = value.toLocaleLowerCase();
  if (field === "business_type") {
    const raw = String(
      lead.business_type || fieldText(lead, "business type", "Business Type", "Industry") || "",
    ).trim();
    return raw.toLocaleLowerCase().includes(folded);
  }
  if (field === "status") {
    return (lead.status || "") === value;
  }
  if (field === "state") {
    return leadStateText(lead).trim().toUpperCase() === value.toUpperCase();
  }
  return true;
}

function leadMatchesSearch(lead, foldedQuery) {
  if (!foldedQuery) return true;
  const haystack = [
    businessLabel(lead),
    lead.name,
    lead.business,
    lead.phone,
    lead.business_type,
    fieldText(lead, "business type", "Business Type", "Industry"),
    leadStateText(lead),
  ]
    .filter(Boolean)
    .join(" ")
    .toLocaleLowerCase();
  return haystack.includes(foldedQuery);
}

function leadMatchesAll(lead) {
  if (!lead?.id) return false;
  if (!leadMatchesFilter(lead)) return false;
  const q = searchQuery.trim().toLocaleLowerCase();
  return leadMatchesSearch(lead, q);
}

function filterCacheKey() {
  return [state.leads_version, filterField(), filterValueText(), searchQuery.trim().toLocaleLowerCase()].join("\u0003");
}

function invalidateMatchingCache() {
  matchingIdCache = null;
}

function catalogLeads() {
  return pickerLeads();
}

/** Collect ids for every prospect that matches the current filter + search (no DOM). */
export function matchingLeadIds() {
  const key = filterCacheKey();
  if (matchingIdCache?.key === key) return matchingIdCache.ids;
  const ids = [];
  for (const lead of catalogLeads()) {
    if (leadMatchesAll(lead)) ids.push(lead.id);
  }
  matchingIdCache = { key, ids };
  return ids;
}

/** Ids to pass into campaign import (visible selection or full matching set). */
export function workflowCrmImportLeadIds() {
  if (selectAllMatching) return matchingLeadIds();
  return [...selectedLeadIds];
}

function resetPagingAndSelection() {
  visibleCount = PAGE_SIZE;
  selectAllMatching = false;
  selectedLeadIds.clear();
  invalidateMatchingCache();
  lastListSignature = "";
}

function scanMatchingLeads(onMatch) {
  let total = 0;
  for (const lead of catalogLeads()) {
    if (!leadMatchesAll(lead)) continue;
    total += 1;
    onMatch(lead, total);
  }
  return total;
}

function sidebarListSignature() {
  const parts = [];
  let shown = 0;
  const limit = visibleCount;
  const total = scanMatchingLeads((lead, index) => {
    if (index <= limit) {
      parts.push(`${lead.id}\u0001${lead.status}\u0001${businessLabel(lead)}`);
      shown = index;
    }
  });
  return [
    filterCacheKey(),
    visibleCount,
    selectAllMatching ? "all" : "pick",
    selectedLeadIds.size,
    total,
    shown,
    parts.join("\u0002"),
  ].join("\u0004");
}

function filterUiSignature() {
  return [filterField(), state.leads_version, catalogLeads().length].join("|");
}

function stateOptions() {
  if (stateOptionsCache.version === state.leads_version) return stateOptionsCache.states;
  const states = new Set();
  for (const lead of catalogLeads()) {
    const code = leadStateText(lead);
    if (code) states.add(code);
  }
  const sorted = [...states].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
  stateOptionsCache = { version: state.leads_version, states: sorted };
  return sorted;
}

function syncSelectionUi() {
  updateSelectedSummary();
  updateListChrome();
  const list = listEl();
  if (!list) return;
  for (const row of list.querySelectorAll("[data-lead-id]")) {
    const cb = row.querySelector('input[type="checkbox"]');
    if (!cb) continue;
    if (selectAllMatching) {
      cb.checked = true;
      cb.indeterminate = false;
    } else {
      cb.checked = selectedLeadIds.has(row.dataset.leadId);
      cb.indeterminate = false;
    }
  }
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
    select.replaceChildren();
    const all = document.createElement("option");
    all.value = "";
    all.textContent = "All states";
    select.append(all);
    for (const code of stateOptions()) {
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

function updateListChrome() {
  const totalMatching = matchingLeadIds().length;
  const showing = Math.min(visibleCount, totalMatching);
  const meta = document.getElementById("workflowCrmListMeta");
  if (meta) {
    if (!totalMatching) {
      const total = catalogLeads().length;
      meta.textContent = total ? "0 match filter" : "0 prospects";
    } else if (showing < totalMatching) {
      meta.textContent = `Showing ${showing} of ${totalMatching}`;
    } else {
      meta.textContent = totalMatching === 1 ? "1 prospect" : `${totalMatching} prospects`;
    }
  }
  const selectAllBtn = document.getElementById("workflowCrmSelectAllMatching");
  if (selectAllBtn) {
    if (totalMatching === 0) {
      selectAllBtn.hidden = true;
    } else {
      selectAllBtn.hidden = false;
      if (selectAllMatching) {
        selectAllBtn.textContent = `All ${totalMatching} matching selected`;
        selectAllBtn.setAttribute("aria-pressed", "true");
      } else {
        selectAllBtn.textContent = `Select all ${totalMatching} matching`;
        selectAllBtn.setAttribute("aria-pressed", "false");
      }
    }
  }
  const loadMore = document.getElementById("workflowCrmLoadMore");
  if (loadMore) {
    const more = totalMatching > visibleCount;
    loadMore.hidden = !more;
    if (more) {
      const next = Math.min(PAGE_SIZE, totalMatching - visibleCount);
      loadMore.textContent = `Load ${next} more`;
    }
  }
}

function updateSelectedSummary() {
  if (selectAllMatching) {
    const n = matchingLeadIds().length;
    setText("workflowCrmSelectedCount", `Selected ${n} (all matching)`);
  } else {
    setText("workflowCrmSelectedCount", `Selected ${selectedLeadIds.size}`);
  }
  const btn = document.getElementById("workflowCrmImportBtn");
  if (btn) {
    const ready = selectAllMatching ? matchingLeadIds().length > 0 : selectedLeadIds.size > 0;
    btn.disabled = !ready;
  }
}

function renderLeadList() {
  const list = listEl();
  if (!list) return;
  list.replaceChildren();
  const totalCatalog = catalogLeads().length;
  const slice = [];
  let totalMatching = 0;
  scanMatchingLeads((lead, index) => {
    totalMatching = index;
    if (index <= visibleCount) slice.push(lead);
  });

  if (!totalMatching) {
    const empty = document.createElement("p");
    empty.className = "workflow-crm-empty";
    empty.textContent = totalCatalog
      ? "No prospects match this filter or search."
      : "No prospects in CRM yet.";
    list.append(empty);
    updateListChrome();
    updateSelectedSummary();
    return;
  }

  for (const lead of slice) {
    const row = document.createElement("div");
    row.className = "workflow-crm-lead-row";
    row.role = "listitem";
    row.dataset.leadId = lead.id;

    const label = document.createElement("label");
    label.className = "workflow-crm-lead-check";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectAllMatching || selectedLeadIds.has(lead.id);
    checkbox.setAttribute("aria-label", `Select ${businessLabel(lead)}`);
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
  updateListChrome();
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

function scheduleSearchRender() {
  if (searchDebounceTimer) window.clearTimeout(searchDebounceTimer);
  searchDebounceTimer = window.setTimeout(() => {
    searchDebounceTimer = null;
    searchQuery = document.getElementById("workflowCrmSearchInput")?.value?.trim() || "";
    resetPagingAndSelection();
    renderWorkflowCrmSidebar();
  }, SEARCH_DEBOUNCE_MS);
}

export function releaseWorkflowCrmSidebarDom() {
  lastListSignature = "";
  lastFilterUiSignature = "";
  visibleCount = PAGE_SIZE;
  searchQuery = "";
  selectAllMatching = false;
  selectedLeadIds.clear();
  matchingIdCache = null;
  if (searchDebounceTimer) {
    window.clearTimeout(searchDebounceTimer);
    searchDebounceTimer = null;
  }
  listEl()?.replaceChildren();
  const search = document.getElementById("workflowCrmSearchInput");
  if (search) search.value = "";
  document.getElementById("workflowCrmLoadMore")?.setAttribute("hidden", "");
  document.getElementById("workflowCrmSelectAllMatching")?.setAttribute("hidden", "");
}

export function renderWorkflowCrmSidebar() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  const filterSig = filterUiSignature();
  if (filterSig !== lastFilterUiSignature) {
    lastFilterUiSignature = filterSig;
    syncFilterValueControls();
  }
  const listSig = sidebarListSignature();
  if (listSig === lastListSignature) {
    syncSelectionUi();
    return;
  }
  lastListSignature = listSig;
  renderLeadList();
}

export function bindWorkflowCrmSidebar() {
  if (sidebarBound) return;
  sidebarBound = true;
  loadPanelWidth();

  listEl()?.addEventListener("change", (event) => {
    const input = event.target;
    if (input?.type !== "checkbox") return;
    const row = input.closest("[data-lead-id]");
    if (!row?.dataset.leadId) return;
    if (selectAllMatching) {
      selectAllMatching = false;
      selectedLeadIds.clear();
    }
    if (input.checked) selectedLeadIds.add(row.dataset.leadId);
    else selectedLeadIds.delete(row.dataset.leadId);
    lastListSignature = "";
    updateSelectedSummary();
    updateListChrome();
    syncSelectionUi();
  });

  document.getElementById("workflowCrmFilterField")?.addEventListener("change", () => {
    document.getElementById("workflowCrmFilterValueSelect").value = "";
    document.getElementById("workflowCrmFilterValueInput").value = "";
    resetPagingAndSelection();
    lastFilterUiSignature = "";
    renderWorkflowCrmSidebar();
  });
  document.getElementById("workflowCrmFilterValueSelect")?.addEventListener("change", () => {
    resetPagingAndSelection();
    renderWorkflowCrmSidebar();
  });
  document.getElementById("workflowCrmFilterValueInput")?.addEventListener("input", () => {
    resetPagingAndSelection();
    renderWorkflowCrmSidebar();
  });
  document.getElementById("workflowCrmSearchInput")?.addEventListener("input", scheduleSearchRender);
  document.getElementById("workflowCrmSearchInput")?.addEventListener("search", () => {
    if (searchDebounceTimer) {
      window.clearTimeout(searchDebounceTimer);
      searchDebounceTimer = null;
    }
    searchQuery = document.getElementById("workflowCrmSearchInput")?.value?.trim() || "";
    resetPagingAndSelection();
    renderWorkflowCrmSidebar();
  });

  document.getElementById("workflowCrmLoadMore")?.addEventListener("click", () => {
    visibleCount += PAGE_SIZE;
    lastListSignature = "";
    renderWorkflowCrmSidebar();
  });

  document.getElementById("workflowCrmSelectAllMatching")?.addEventListener("click", () => {
    if (selectAllMatching) {
      selectAllMatching = false;
      selectedLeadIds.clear();
    } else {
      selectAllMatching = true;
      selectedLeadIds.clear();
    }
    lastListSignature = "";
    renderWorkflowCrmSidebar();
  });

  document.getElementById("workflowCrmResizer")?.addEventListener("pointerdown", startPanelResize);
  document.getElementById("workflowCrmImportBtn")?.addEventListener("click", () => {
    const ids = workflowCrmImportLeadIds();
    if (ids.length) {
      // Step 3: import preview + membership for all ids (including off-screen rows).
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