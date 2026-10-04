import { postJson } from "../api/client.js";
import { state } from "../store/state.js";
import { byId, setText } from "../utils/format.js";
import { openTranscript } from "../utils/transcript.js";
import { showToast } from "./dialogs.js";
import { render } from "./render.js";

export async function selectTimezone(timezone) {
  try {
    Object.assign(state, await postJson("/api/timezone", { timezone: timezone || "" }));
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}

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
}

export function renderCallerPool() {
  const pool = state.pool || [];
  renderTimezoneFilters();
  setText("poolTabCount", String(pool.length));
  setText("poolTableSummary", `${pool.length} new prospect${pool.length === 1 ? "" : "s"}${state.selected_timezone ? ` · ${state.selected_timezone}` : ""}${state.skipped_outside_hours ? ` · ${state.skipped_outside_hours} skipped: outside calling hours` : ""}${state.skipped_unknown_timezone ? ` · ${state.skipped_unknown_timezone} skipped: timezone unavailable` : ""}`);
  const body = byId("poolTableBody");
  body.replaceChildren(...pool.map((lead) => {
    const row = document.createElement("tr");
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

export function bindCallerPool() {
  for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
    selector.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
}
