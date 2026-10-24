import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { CRM_STATUS_KEYS, STATUS_LABELS, STATUS_STYLES, crmStatusOptionText, fillTimezoneSelect, initials, leavesQueueForGood, markCallback } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { LEAD_COLUMNS, locationText } from "./query.js";
import { openTranscript } from "./transcript.js";

export function appendLeadRows(body, leads, extras, onSelection) {
  for (const lead of leads) {
    const row = document.createElement("tr");
    row.dataset.leadId = lead.id;
    const blocked = lead.status === "disqualified" || lead.status === "no_answer_disqualified";
    row.title = blocked ? "Will not be dialed" : lead.phone ? "Right-click to dial" : "No phone number";
    row.classList.toggle("selected", selectedLeadIds.has(lead.id));
    const selectionCell = document.createElement("td");
    selectionCell.className = "selection-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "prospect-checkbox";
    checkbox.checked = selectedLeadIds.has(lead.id);
    checkbox.setAttribute("aria-label", `Select ${lead.name || lead.phone || "prospect"}`);
    checkbox.addEventListener("click", (event) => {
      const targetIndex = leads.findIndex((item) => item.id === lead.id);
      const anchorIndex = leads.findIndex((item) => item.id === selection.anchorId);
      if (event.shiftKey && anchorIndex >= 0 && targetIndex >= 0) {
        const start = Math.min(anchorIndex, targetIndex);
        const end = Math.max(anchorIndex, targetIndex);
        for (const item of leads.slice(start, end + 1)) {
          if (checkbox.checked) selectedLeadIds.add(item.id);
          else selectedLeadIds.delete(item.id);
        }
      } else if (checkbox.checked) {
        selectedLeadIds.add(lead.id);
      } else {
        selectedLeadIds.delete(lead.id);
      }
      selection.anchorId = lead.id;
      onSelection();
    });
    selectionCell.append(checkbox);
    row.append(selectionCell);

    for (const column of LEAD_COLUMNS) appendLeadColumn(row, lead, column);

    for (const column of extras) {
      row.append(dataCell(fieldInput(lead, "fields", lead.fields?.[column] || "", column, column)));
    }

    const transcriptCell = document.createElement("td");
    const transcriptButton = document.createElement("button");
    const transcriptCount = lead.transcript?.length || 0;
    transcriptButton.type = "button";
    transcriptButton.className = "transcript-view-button";
    transcriptButton.textContent = transcriptCount ? `View · ${transcriptCount}` : "No transcript";
    transcriptButton.disabled = transcriptCount === 0;
    transcriptButton.setAttribute("aria-label", transcriptCount ? `View ${transcriptCount} transcript utterances for ${lead.name || lead.phone}` : `No transcript for ${lead.name || lead.phone}`);
    transcriptButton.addEventListener("click", () => openTranscript(lead));
    transcriptCell.append(transcriptButton);
    row.append(transcriptCell);
    body.append(row);
  }
}

function statusCell(lead) {
  const cell = document.createElement("td");
  cell.className = "status-cell";
  const select = document.createElement("select");
  const currentStatus = lead.status || "new";
  select.className = `status-select status-${STATUS_STYLES[currentStatus]?.className || "neutral"}`;
  select.setAttribute("aria-label", `Call status for ${lead.name || lead.phone}`);
  if (!CRM_STATUS_KEYS.includes(currentStatus)) {
    const current = document.createElement("option");
    current.value = currentStatus;
    current.textContent = STATUS_LABELS[currentStatus] || currentStatus;
    current.selected = true;
    current.disabled = true;
    select.append(current);
  }
  for (const value of CRM_STATUS_KEYS) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = crmStatusOptionText(value, lead);
    option.selected = currentStatus === value;
    if (value === "new" && state.pending_outcome?.id === lead.id) option.disabled = true;
    if (leavesQueueForGood(lead, value)) option.disabled = true;
    select.append(option);
  }
  select.addEventListener("change", () => {
    const next = String(select.value || "").trim();
    if (!next || !CRM_STATUS_KEYS.includes(next)) {
      select.value = currentStatus;
      return;
    }
    const current = state.leads.find((item) => item.id === lead.id) || lead;
    document.dispatchEvent(new CustomEvent("prospect-status", {
      detail: { lead: current, status: next, select },
    }));
  });
  markCallback(select, lead);
  cell.append(select);
  return cell;
}

function appendLeadColumn(row, lead, column) {
  if (column.key === "status") {
    row.append(statusCell(lead));
    return;
  }
  if (column.key === "name") {
    row.append(prospectCell(lead));
    return;
  }
  if (column.key === "business") {
    row.append(dataCell(fieldInput(lead, "business", lead.business || "", "Company")));
    return;
  }
  if (column.key === "state") {
    row.append(dataCell(fieldInput(lead, "state", locationText(lead, "state"), "State")));
    return;
  }
  if (column.key === "city") {
    row.append(dataCell(fieldInput(lead, "city", locationText(lead, "city"), "City")));
    return;
  }
  if (column.key === "phone") {
    row.append(phoneCell(lead));
    return;
  }
  if (column.key === "timezone") {
    row.append(dataCell(timezoneInput(lead)));
    return;
  }
  if (column.key === "review_pct_30_days") {
    row.append(metricCell(formatPercent(lead.review_pct_30_days)));
    return;
  }
  if (column.kind === "number") {
    row.append(metricCell(formatCount(lead[column.key])));
    return;
  }
  row.append(metricCell(lead.recency_source || "—"));
}

function prospectCell(lead) {
  const contact = document.createElement("td");
  const contactWrap = document.createElement("div");
  contactWrap.className = "contact-cell";
  const avatar = document.createElement("span");
  avatar.className = "contact-avatar";
  avatar.textContent = initials(lead.name || lead.business);
  const copy = document.createElement("span");
  copy.className = "contact-copy";
  const name = fieldInput(lead, "name", lead.name || "", "Prospect name");
  const subline = document.createElement("span");
  subline.textContent = lead.business || "Prospect";
  copy.append(name, subline);
  contactWrap.append(avatar, copy);
  contact.append(contactWrap);
  return contact;
}

function phoneCell(lead) {
  const cell = document.createElement("td");
  cell.className = "phone-cell";
  if (!lead.phone) {
    cell.textContent = "—";
    return cell;
  }
  const link = document.createElement("a");
  link.className = "phone-link";
  link.href = `tel:${lead.phone}`;
  link.textContent = formatPhoneNumber(lead.phone);
  cell.title = link.textContent;
  cell.append(link);
  return cell;
}

function metricCell(text) {
  const cell = document.createElement("td");
  cell.className = "metric-cell";
  cell.textContent = text;
  return cell;
}

function formatCount(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  return Number.isFinite(number) ? String(number) : "—";
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "") return "—";
  const number = Number(value);
  if (!Number.isFinite(number)) return "—";
  const rounded = Math.round(number * 1000) / 1000;
  const text = Number.isInteger(rounded) ? String(rounded) : String(rounded);
  return `${text}%`;
}

function dataCell(control) {
  const cell = document.createElement("td");
  cell.append(control);
  return cell;
}

function fieldInput(lead, field, value, label, extra = "") {
  const input = document.createElement("input");
  input.type = "text";
  input.className = "cell-editor";
  input.value = value;
  input.placeholder = "—";
  input.autocomplete = "off";
  input.setAttribute("aria-label", `${label} for ${lead.name || lead.business || lead.phone || "prospect"}`);
  bindFieldEditor(input, { lead, field, extra });
  return input;
}

function timezoneInput(lead) {
  const select = document.createElement("select");
  select.className = "cell-editor";
  select.setAttribute("aria-label", `Timezone for ${lead.name || lead.business || lead.phone || "prospect"}`);
  fillTimezoneSelect(select, lead.timezone || "Unknown");
  bindFieldEditor(select, { lead, field: "timezone" });
  return select;
}

function bindFieldEditor(input, detail) {
  input.dataset.savedValue = input.value;
  if (input.tagName !== "SELECT") {
    input.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        input.value = input.dataset.savedValue;
        event.preventDefault();
        input.blur();
      } else if (event.key === "Enter") {
        event.preventDefault();
        input.blur();
      }
    });
  }
  input.addEventListener("change", () => {
    const value = input.value.trim();
    if (value === input.dataset.savedValue) {
      input.value = input.dataset.savedValue;
      return;
    }
    document.dispatchEvent(new CustomEvent("prospect-field", {
      detail: { ...detail, value, previous: input.dataset.savedValue, input },
    }));
  });
  input.addEventListener("blur", () => {
    document.dispatchEvent(new CustomEvent("prospect-field-blur"));
  });
}
