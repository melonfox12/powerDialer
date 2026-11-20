import { selectedLeadIds, selection } from "./selection.js";
import { createCrmStatusSelect, fillTimezoneSelect } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { LEAD_COLUMNS, fieldText, locationText, pitchSegmentText, splitName } from "./query.js";

const LINKEDIN_FIELD = "LinkedIn profile";
const WEBSITE_FIELD = "Website";
import { appendNotesCell } from "../../_core/notes.js";
import { openTranscript } from "./transcript.js";

export function appendLeadRows(body, leads, extras, onSelection) {
  for (const lead of leads) {
    const row = document.createElement("tr");
    row.dataset.leadId = lead.id;
    const blocked = lead.status === "closed";
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

    appendNotesCell(row, lead, { compact: true });

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
  cell.append(createCrmStatusSelect(lead));
  return cell;
}

function appendLeadColumn(row, lead, column) {
  if (column.key === "status") {
    row.append(statusCell(lead));
    return;
  }
  if (column.key === "first_name") {
    row.append(namePartCell(lead, "first"));
    return;
  }
  if (column.key === "last_name") {
    row.append(namePartCell(lead, "last"));
    return;
  }
  if (column.key === "linkedin") {
    row.append(dataCell(fieldInput(
      lead,
      "fields",
      fieldText(lead, LINKEDIN_FIELD, "LinkedIn", "linkedin profile", "linkedin"),
      "LinkedIn profile",
      LINKEDIN_FIELD,
    )));
    return;
  }
  if (column.key === "website") {
    row.append(dataCell(fieldInput(
      lead,
      "fields",
      fieldText(lead, WEBSITE_FIELD, "website", "url"),
      "Website",
      WEBSITE_FIELD,
    )));
    return;
  }
  if (column.key === "business_type") {
    row.append(dataCell(fieldInput(lead, "business_type", lead.business_type || "", "Business type")));
    return;
  }
  if (column.key === "business") {
    row.append(dataCell(fieldInput(lead, "business", lead.business || "", "Company")));
    return;
  }
  if (column.key === "pitch_segment") {
    row.append(dataCell(fieldInput(lead, "pitch_segment", pitchSegmentText(lead), "Pitch segment")));
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
  if (column.kind === "number") {
    row.append(metricCell(formatCount(lead[column.key])));
    return;
  }
  row.append(metricCell("—"));
}

function namePartCell(lead, part) {
  const { first, last } = splitName(lead.name);
  const value = part === "first" ? first : last;
  const label = part === "first" ? "First name" : "Last name";
  const input = document.createElement("input");
  input.type = "text";
  input.className = "cell-editor";
  input.value = value;
  input.placeholder = "—";
  input.autocomplete = "off";
  input.setAttribute("aria-label", `${label} for ${lead.name || lead.business || lead.phone || "prospect"}`);
  input.dataset.savedValue = value;
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
  input.addEventListener("change", () => {
    const trimmed = input.value.trim();
    if (trimmed === input.dataset.savedValue) {
      input.value = input.dataset.savedValue;
      return;
    }
    const other = splitName(lead.name)[part === "first" ? "last" : "first"];
    const nextFirst = part === "first" ? trimmed : other;
    const nextLast = part === "last" ? trimmed : other;
    const value = [nextFirst, nextLast].filter(Boolean).join(" ");
    document.dispatchEvent(new CustomEvent("prospect-field", {
      detail: { lead, field: "name", value, previous: lead.name || "", input },
    }));
  });
  input.addEventListener("blur", () => {
    document.dispatchEvent(new CustomEvent("prospect-field-blur"));
  });
  const cell = document.createElement("td");
  cell.append(input);
  return cell;
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
