import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { byId, setText } from "../../_core/format.js";
import { appendLeadRows } from "./rows.js";
import { crmTableSignature, filteredLeads, importedColumns } from "./query.js";

let lastCrmTableSignature = null;

export function renderTableIfStale() {
  if (crmTableSignature() !== lastCrmTableSignature) renderTable();
}

export function renderTable() {
  lastCrmTableSignature = crmTableSignature();
  const head = byId("tableHead");
  const body = byId("tableBody");
  const leads = filteredLeads();
  const extras = importedColumns();
  const currentLeadIds = new Set(state.leads.map((lead) => lead.id));
  for (const id of selectedLeadIds) {
    if (!currentLeadIds.has(id)) selectedLeadIds.delete(id);
  }
  if (!currentLeadIds.has(selection.anchorId)) selection.anchorId = null;
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
  appendLeadRows(body, leads, extras, renderTable);
  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV or add a prospect to start your workspace."
    : "Change the search or status filter to see more rows.";
  byId("crmTable").hidden = state.leads.length === 0;
  const summary = `${leads.length} of ${state.leads.length} prospect${state.leads.length === 1 ? "" : "s"}`;
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}
