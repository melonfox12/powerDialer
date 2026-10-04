import { changeLeadStatus } from "../controllers/prospects.js";
import { S, selectedLeadIds, state } from "../store/state.js";
import { STATUS_LABELS, STATUS_STYLES, byId, initials, setText, statusDate } from "../utils/format.js";
import { formatPhoneNumber } from "../utils/phone.js";
import { openTranscript } from "../utils/transcript.js";

export function importedColumns() {
  const columns = [];
  const standard = /^(name|full name|contact|first name|last name|business|company|organization|organisation|phone(?: number| e\.?164)?|mobile|cell|telephone|time\s?zone|tz|call.?status|status)$/i;
  for (const lead of state.leads) {
    for (const key of Object.keys(lead.fields || {})) {
      if (!standard.test(key) && !columns.includes(key)) columns.push(key);
    }
  }
  return columns;
}

export function filteredLeads() {
  const query = byId("searchInput").value.trim().toLocaleLowerCase();
  const filter = byId("statusFilter").value;
  return state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (!query) return true;
    const values = [lead.name, lead.business, lead.phone, lead.status, ...Object.values(lead.fields || {})];
    return values.some((value) => String(value || "").toLocaleLowerCase().includes(query));
  });
}

export function crmTableSignature() {
  return JSON.stringify([
    state.pending_outcome?.id || null,
    state.leads.map((lead) => [
      lead.id,
      lead.name,
      lead.business,
      lead.phone,
      lead.timezone,
      lead.status,
      lead.scheduled_until,
      lead.fields,
      lead.transcript?.length || 0,
    ]),
  ]);
}

export function renderTable() {
  S.lastCrmTableSignature = crmTableSignature();
  const head = byId("tableHead");
  const body = byId("tableBody");
  const leads = filteredLeads();
  const extras = importedColumns();
  const currentLeadIds = new Set(state.leads.map((lead) => lead.id));
  for (const id of selectedLeadIds) {
    if (!currentLeadIds.has(id)) selectedLeadIds.delete(id);
  }
  if (!currentLeadIds.has(S.selectionAnchorId)) S.selectionAnchorId = null;
  head.replaceChildren();
  body.replaceChildren();

  const selectAllCell = document.createElement("th");
  selectAllCell.className = "selection-cell";
  selectAllCell.scope = "col";
  const selectAll = document.createElement("input");
  selectAll.type = "checkbox";
  selectAll.className = "prospect-checkbox";
  selectAll.setAttribute("aria-label", "Select all visible prospects");
  const selectedVisibleCount = leads.filter((lead) => selectedLeadIds.has(lead.id)).length;
  selectAll.checked = leads.length > 0 && selectedVisibleCount === leads.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < leads.length;
  selectAll.addEventListener("change", () => {
    for (const lead of leads) {
      if (selectAll.checked) selectedLeadIds.add(lead.id);
      else selectedLeadIds.delete(lead.id);
    }
    renderTable();
  });
  selectAllCell.append(selectAll);
  head.append(selectAllCell);

  for (const label of ["Prospect", "Company", "Phone Number", "Timezone", ...extras, "Call status", "Call transcript"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }

  for (const lead of leads) {
    const row = document.createElement("tr");
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
      renderTable();
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
    select.addEventListener("change", () => changeLeadStatus(lead, select.value, select));
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

  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV to add prospects to your workspace."
    : "Change the search or status filter to see more rows.";
  byId("crmTable").hidden = state.leads.length === 0;
  const summary = `${leads.length} of ${state.leads.length} prospect${state.leads.length === 1 ? "" : "s"}`;
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}
