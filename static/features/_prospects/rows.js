import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { STATUS_KEYS, STATUS_LABELS, STATUS_STYLES, fillTimezoneSelect, initials, statusDate } from "../../_core/format.js";
import { locationText } from "./query.js";
import { openTranscript } from "./transcript.js";

export function appendLeadRows(body, leads, extras, onSelection) {
  for (const lead of leads) {
    const row = document.createElement("tr");
    row.dataset.leadId = lead.id;
    row.title = lead.status === "do_not_call" ? "Marked do not call" : lead.phone ? "Right-click to dial" : "No phone number";
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
    row.append(contact);

    row.append(dataCell(fieldInput(lead, "business", lead.business || "", "Company")));
    row.append(dataCell(fieldInput(lead, "state", locationText(lead, "state"), "State")));
    row.append(dataCell(fieldInput(lead, "city", locationText(lead, "city"), "City")));
    const phone = fieldInput(lead, "phone", lead.phone || "", "Phone number");
    phone.type = "tel";
    const phoneCell = dataCell(phone);
    phoneCell.className = "phone-cell";
    phoneCell.title = lead.phone || "";
    row.append(phoneCell);
    row.append(dataCell(timezoneInput(lead)));

    for (const column of extras) {
      row.append(dataCell(fieldInput(lead, "fields", lead.fields?.[column] || "", column, column)));
    }

    const statusCell = document.createElement("td");
    statusCell.className = "status-cell";
    const select = document.createElement("select");
    select.className = `status-select status-${STATUS_STYLES[lead.status]?.className || "neutral"}`;
    select.setAttribute("aria-label", `Call status for ${lead.name || lead.phone}`);
    for (const value of STATUS_KEYS) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "call" && statusDate(lead) ? `Callback (${statusDate(lead)})` : STATUS_LABELS[value];
      option.selected = lead.status === value;
      if (value === "new" && state.pending_outcome?.id === lead.id) option.disabled = true;
      select.append(option);
    }
    select.addEventListener("change", () => {
      document.dispatchEvent(new CustomEvent("prospect-status", {
        detail: { lead, status: select.value, select },
      }));
    });
    statusCell.append(select);
    row.append(statusCell);

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
