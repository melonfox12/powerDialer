import { S, selectedLeadIds, state } from "../../store/state.js";
import { STATUS_LABELS, STATUS_STYLES, initials, statusDate } from "../../utils/format.js";
import { formatPhoneNumber } from "../../utils/phone.js";
import { openTranscript } from "../../utils/transcript.js";

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
      const anchorIndex = leads.findIndex((item) => item.id === S.selectionAnchorId);
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
      S.selectionAnchorId = lead.id;
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
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const subline = document.createElement("span");
    subline.textContent = lead.business || "Prospect";
    copy.append(name, subline);
    contactWrap.append(avatar, copy);
    contact.append(contactWrap);
    row.append(contact);

    for (const value of [lead.business, lead.phone, lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value === lead.phone ? formatPhoneNumber(lead.phone) : value || "—";
      if (value === lead.phone) {
        cell.className = "phone-cell";
        cell.title = lead.phone || "";
      }
      row.append(cell);
    }

    for (const column of extras) {
      const cell = document.createElement("td");
      cell.title = lead.fields?.[column] || "";
      cell.textContent = lead.fields?.[column] || "—";
      row.append(cell);
    }

    const statusCell = document.createElement("td");
    statusCell.className = "status-cell";
    const select = document.createElement("select");
    select.className = `status-select status-${STATUS_STYLES[lead.status]?.className || "neutral"}`;
    select.setAttribute("aria-label", `Call status for ${lead.name || lead.phone}`);
    for (const value of ["new", "call", "booked", "interested", "disqualified", "do_not_call"]) {
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
