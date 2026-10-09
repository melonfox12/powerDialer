import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { byId, setText } from "../../_core/format.js";
import { appendLeadRows } from "./rows.js";
import { crmTableSignature, currentColumnSort, filteredLeads, importedColumns, setColumnSort } from "./query.js";

const SORTABLE_COLUMNS = { Company: "business", State: "state", City: "city" };

let lastCrmTableSignature = null;

export function renderTableIfStale() {
  if (fieldEditorFocused()) return;
  if (crmTableSignature() !== lastCrmTableSignature) renderTable();
}

document.addEventListener("prospect-field-blur", () => {
  queueMicrotask(() => renderTableIfStale());
});

function headerCell(label) {
  const cell = document.createElement("th");
  cell.scope = "col";
  cell.textContent = label;
  const sortKey = SORTABLE_COLUMNS[label];
  if (!sortKey) return cell;
  const active = currentColumnSort();
  cell.classList.add("sortable-column");
  cell.title = "Right-click to sort";
  if (active?.key === sortKey) {
    cell.setAttribute("aria-sort", active.direction === "desc" ? "descending" : "ascending");
    const mark = document.createElement("span");
    mark.className = "column-sort-mark";
    mark.textContent = active.direction === "desc" ? "Z–A" : "A–Z";
    cell.append(mark);
  }
  cell.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openColumnSortMenu(sortKey, event.clientX, event.clientY);
  });
  return cell;
}

let sortMenu = null;

function openColumnSortMenu(key, x, y) {
  const menu = ensureSortMenu();
  const dialMenu = document.getElementById("prospectMenu");
  if (dialMenu) dialMenu.hidden = true;
  const active = currentColumnSort();
  menu.replaceChildren();
  for (const [direction, text] of [["asc", "Sort A–Z"], ["desc", "Sort Z–A"]]) {
    const button = document.createElement("button");
    button.type = "button";
    button.setAttribute("role", "menuitemradio");
    button.setAttribute("aria-checked", active?.key === key && active.direction === direction ? "true" : "false");
    button.textContent = text;
    button.addEventListener("click", () => {
      setColumnSort(key, direction);
      menu.hidden = true;
      renderTable();
    });
    menu.append(button);
  }
  menu.hidden = false;
  menu.style.left = "0px";
  menu.style.top = "0px";
  const rect = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(8, Math.min(x, window.innerWidth - rect.width - 8))}px`;
  menu.style.top = `${Math.max(8, Math.min(y, window.innerHeight - rect.height - 8))}px`;
  menu.querySelector("button")?.focus();
}

function ensureSortMenu() {
  if (sortMenu) return sortMenu;
  sortMenu = document.createElement("div");
  sortMenu.id = "columnSortMenu";
  sortMenu.className = "prospect-menu";
  sortMenu.hidden = true;
  sortMenu.setAttribute("role", "menu");
  document.body.append(sortMenu);
  document.addEventListener("click", (event) => {
    if (sortMenu.hidden || sortMenu.contains(event.target)) return;
    sortMenu.hidden = true;
  });
  document.addEventListener("keydown", (event) => {
    if (sortMenu.hidden || event.key !== "Escape") return;
    event.preventDefault();
    sortMenu.hidden = true;
  }, true);
  document.addEventListener("scroll", () => {
    if (!sortMenu.hidden) sortMenu.hidden = true;
  }, true);
  return sortMenu;
}

function fieldEditorFocused() {
  const active = document.activeElement;
  return active instanceof HTMLElement && active.classList.contains("cell-editor") && byId("crmTable")?.contains(active);
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

  for (const label of ["Prospect", "Company", "State", "City", "Phone Number", "Timezone", ...extras, "Call status", "Call transcript"]) {
    head.append(headerCell(label));
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
