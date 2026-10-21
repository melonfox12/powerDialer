import { state } from "../../_core/state.js";
import { byId, setText } from "../../_core/format.js";
import { openTranscript } from "../../_core/transcript.js";

export function renderTimezoneFilters() {
  const groups = state.timezone_groups || [];
  const totalNew = groups.reduce((sum, group) => sum + group.count, 0);
  const selected = state.selected_timezone || "";
  const knownZones = groups.map((group) => group.name);
  const options = [new Option(`All time zones (${totalNew})`, "")];
  if (selected && !knownZones.includes(selected)) options.push(new Option(selected, selected));
  options.push(...groups.map((group) => new Option(`${group.name} (${group.count})`, group.name)));
  for (const select of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")].filter(Boolean)) {
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    select.value = selected;
  }
  syncDialerTimezoneMenu();
}

function syncDialerTimezoneMenu() {
  const select = byId("dialerTimezoneFilter");
  const button = byId("dialerTimezoneButton");
  const list = byId("dialerTimezoneList");
  if (!select || !button || !list) return;
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

export function bindDialerTimezoneMenu() {
  const button = byId("dialerTimezoneButton");
  const list = byId("dialerTimezoneList");
  const select = byId("dialerTimezoneFilter");
  button.addEventListener("click", () => {
    const open = list.hidden;
    list.hidden = !open;
    button.setAttribute("aria-expanded", open ? "true" : "false");
  });
  list.addEventListener("click", (event) => {
    const item = event.target.closest(".timezone-menu-option");
    if (!item) return;
    select.value = item.dataset.value;
    select.dispatchEvent(new Event("change", { bubbles: true }));
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".timezone-menu")) {
      list.hidden = true;
      button.setAttribute("aria-expanded", "false");
    }
  });
  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || list.hidden) return;
    list.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.focus();
  });
}

export function renderCallerPool() {
  const pool = state.pool || [];
  renderTimezoneFilters();
  setText("poolTabCount", String(pool.length));
  setText("poolTableSummary", `${pool.length} new prospect${pool.length === 1 ? "" : "s"}${state.selected_timezone ? ` · ${state.selected_timezone}` : ""}`);
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
    statusLabel.className = "pool-new-status";
    statusLabel.textContent = "New";
    status.append(statusLabel);
    row.append(status);
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
