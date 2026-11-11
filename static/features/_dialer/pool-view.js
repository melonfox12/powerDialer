import { state } from "../../_core/state.js";
import {
  byId,
  CRM_STATUS_LABELS,
  CALLER_ID_GROUPS,
  DEFAULT_CALLER_ID_GROUP,
  DEFAULT_DIAL_POOL_STATUS,
  DIAL_POOL_STATUSES,
  DIAL_POOL_STATUS_LABELS,
  dialerEls,
  setText,
} from "../../_core/format.js";
import { appendNotesCell, notesEditorFocused } from "../../_core/notes.js";
import { openTranscript } from "../../_core/transcript.js";

export function renderPoolStatusFilters() {
  const keys = DIAL_POOL_STATUSES;
  const labels = DIAL_POOL_STATUS_LABELS;
  const selected = state.dial_pool_status || DEFAULT_DIAL_POOL_STATUS;
  const options = keys.map((key) => new Option(labels[key] || key, key));
  for (const select of [...dialerEls("dialerPoolStatusFilter"), document.getElementById("poolStatusFilter")].filter(Boolean)) {
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    select.value = keys.includes(selected) ? selected : "new";
  }
}

function industryFilterOptions() {
  const fromCatalog = state.business_type_options;
  if (Array.isArray(fromCatalog) && fromCatalog.length) {
    return fromCatalog.map((value) => String(value).trim()).filter(Boolean);
  }
  const seen = new Map();
  for (const lead of state.leads || []) {
    const value = String(lead.business_type || "").trim();
    if (!value) continue;
    const folded = value.toLowerCase();
    if (!seen.has(folded)) seen.set(folded, value);
  }
  return [...seen.values()].sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
}

export function renderBusinessTypeFilter() {
  const selects = dialerEls("dialerBusinessTypeFilter");
  if (!selects.length) return;
  const selected = state.selected_business_type || "";
  const industries = industryFilterOptions();
  const known = industries.map((value) => value.toLowerCase());
  const options = [new Option("All industries", "")];
  options.push(...industries.map((value) => new Option(value, value)));
  if (selected && !known.includes(selected.toLowerCase())) {
    options.push(new Option(selected, selected));
  }
  const value = selected && (known.includes(selected.toLowerCase()) || selected) ? selected : "";
  for (const select of selects) {
    select.replaceChildren(...options.map((o) => o.cloneNode(true)));
    select.value = value;
  }
}

export function renderCallerIdGroupStatus() {
  const selects = dialerEls("dialerCallerIdGroup");
  if (!selects.length) return;
  const selectedKey = state.caller_id_group || DEFAULT_CALLER_ID_GROUP;
  const keys = CALLER_ID_GROUPS.map((item) => item.key);
  const options = CALLER_ID_GROUPS.map((item) => new Option(`Caller ID · ${item.label}`, item.key));
  const value = keys.includes(selectedKey) ? selectedKey : DEFAULT_CALLER_ID_GROUP;
  const disabled = Boolean(
    state.active_lead_id || state.active_lead || state.pending_outcome_id || state.pending_outcome
    || (state.in_flight && state.in_flight.length),
  );
  for (const select of selects) {
    select.replaceChildren(...options.map((o) => o.cloneNode(true)));
    select.value = value;
    select.disabled = disabled;
  }
}

export function renderTimezoneFilters() {
  renderPoolStatusFilters();
  renderBusinessTypeFilter();
  renderCallerIdGroupStatus();
  const groups = state.timezone_groups || [];
  const totalNew = groups.reduce((sum, group) => sum + group.count, 0);
  const selected = state.selected_timezone || "";
  const knownZones = groups.map((group) => group.name);
  const options = [new Option(`All time zones (${totalNew})`, "")];
  if (selected && !knownZones.includes(selected)) options.push(new Option(selected, selected));
  options.push(...groups.map((group) => new Option(`${group.name} (${group.count})`, group.name)));
  for (const select of [...dialerEls("dialerTimezoneFilter"), document.getElementById("poolTimezoneFilter")].filter(Boolean)) {
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    select.value = selected;
  }
  syncDialerTimezoneMenu();
}

function syncDialerTimezoneMenu() {
  const selects = dialerEls("dialerTimezoneFilter");
  const buttons = dialerEls("dialerTimezoneButton");
  const lists = dialerEls("dialerTimezoneList");
  for (let i = 0; i < selects.length; i++) {
    const select = selects[i];
    const button = buttons[i];
    const list = lists[i];
    if (!select || !button || !list) continue;
    const chosen = select.selectedOptions[0];
    button.textContent = chosen ? chosen.textContent : "All time zones";
    list.replaceChildren(...[...select.options].map((option) => {
      const item = document.createElement("li");
      item.className = "timezone-menu-option";
      item.role = "option";
      item.dataset.value = option.value;
      item.textContent = option.textContent;
      item.setAttribute("aria-selected", option.value === select.value ? "true" : "false");
      return item;
    }));
  }
}

let timezoneMenuGlobalBound = false;
let perMenuTimezoneBound = false;

export function bindDialerTimezoneMenu() {
  if (perMenuTimezoneBound) return;
  perMenuTimezoneBound = true;
  const menus = [];
  for (const select of dialerEls("dialerTimezoneFilter")) {
    const menuRoot = select.closest(".timezone-menu");
    const button = menuRoot?.querySelector(".timezone-menu-button");
    const list = menuRoot?.querySelector(".timezone-menu-list");
    if (menuRoot && button && list) menus.push({ button, list, select });
  }
  if (!timezoneMenuGlobalBound) {
    timezoneMenuGlobalBound = true;
    document.addEventListener("click", (event) => {
      if (event.target.closest(".timezone-menu")) return;
      for (const list of dialerEls("dialerTimezoneList")) {
        list.hidden = true;
      }
      for (const button of dialerEls("dialerTimezoneButton")) {
        button.setAttribute("aria-expanded", "false");
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      const openList = dialerEls("dialerTimezoneList").find((node) => !node.hidden);
      if (!openList) return;
      openList.hidden = true;
      const menu = openList.closest(".timezone-menu");
      const btn = menu?.querySelector(".timezone-menu-button");
      btn?.setAttribute("aria-expanded", "false");
      btn?.focus();
    });
  }
  for (const { button, list, select } of menus) {
    button.addEventListener("click", () => {
      const open = list.hidden;
      list.hidden = !open;
      button.setAttribute("aria-expanded", open ? "true" : "false");
    });
    list.addEventListener("click", (event) => {
      const item = event.target.closest(".timezone-menu-option");
      if (!item) return;
      select.value = item.dataset.value;
      syncDialerTimezoneMenu();
      select.dispatchEvent(new Event("change", { bubbles: true }));
      list.hidden = true;
      button.setAttribute("aria-expanded", "false");
    });
  }
}

export function renderCallerPool() {
  if (notesEditorFocused("poolTable")) return;
  const pool = state.pool || [];
  renderTimezoneFilters();
  setText("poolTabCount", String(pool.length));
  const poolLabel = DIAL_POOL_STATUS_LABELS[state.dial_pool_status || DEFAULT_DIAL_POOL_STATUS] || "New";
  const typeSuffix = state.selected_business_type ? ` · ${state.selected_business_type}` : "";
  const zoneSuffix = state.selected_timezone ? ` · ${state.selected_timezone}` : "";
  setText("poolTableSummary", `${pool.length} ${poolLabel} prospect${pool.length === 1 ? "" : "s"}${typeSuffix}${zoneSuffix}`);
  const emptyHint = byId("poolTableEmptyHint");
  if (emptyHint) emptyHint.textContent = `Only prospects marked ${poolLabel} appear in this pool.`;
  const body = byId("poolTableBody");
  body.replaceChildren(...pool.map((lead) => {
    const row = document.createElement("tr");
    row.dataset.leadId = lead.id;
    row.title = lead.phone ? "Right-click to dial" : "No phone number";
    const prospect = document.createElement("td");
    const contact = document.createElement("div");
    contact.className = "contact-copy";
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const detail = document.createElement("span");
    detail.textContent = lead.business || "Prospect";
    contact.append(name, detail);
    prospect.append(contact);
    row.append(prospect);
    for (const value of [lead.business || "—", lead.phone || "—", lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (value === lead.phone) cell.className = "phone-cell";
      row.append(cell);
    }
    const status = document.createElement("td");
    const statusLabel = document.createElement("span");
    statusLabel.className = `pool-new-status pool-status-${lead.status || "new"}`;
    statusLabel.textContent = CRM_STATUS_LABELS[lead.status] || lead.status || "New";
    status.append(statusLabel);
    row.append(status);
    appendNotesCell(row, lead, { compact: true });
    const transcript = document.createElement("td");
    const button = document.createElement("button");
    const count = lead.transcript?.length || 0;
    button.type = "button";
    button.className = "transcript-view-button";
    button.textContent = count ? `View · ${count}` : "No transcript";
    button.disabled = count === 0;
    button.addEventListener("click", () => openTranscript(lead));
    transcript.append(button);
    row.append(transcript);
    return row;
  }));
  byId("poolTable").hidden = pool.length === 0;
  byId("poolTableEmpty").classList.toggle("visible", pool.length === 0);
}
