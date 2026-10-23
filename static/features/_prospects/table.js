import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { byId, setText } from "../../_core/format.js";
import { setDashboardTab } from "../../core.js";
import { appendLeadRows } from "./rows.js";
import { LEAD_COLUMNS, TRAILING_COLUMNS, crmTableSignature, currentColumnSort, filteredLeads, importedColumns, setColumnSort, syncStateFilter, toggleColumnSort } from "./query.js";

let lastCrmTableSignature = null;

export function focusProspect(leadId) {
  if (!leadId) return;
  setDashboardTab("prospects");
  queueMicrotask(() => {
    const row = document.querySelector(`#tableBody tr[data-lead-id="${leadId}"]`);
    if (!row) return;
    row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    row.classList.add("prospect-menu-target");
    setTimeout(() => row.classList.remove("prospect-menu-target"), 2000);
  });
}

export function renderTableIfStale() {
  if (fieldEditorFocused()) return;
  if (crmTableSignature() !== lastCrmTableSignature) renderTable();
}

document.addEventListener("prospect-field-blur", () => {
  queueMicrotask(() => renderTableIfStale());
});

function headerCell(column) {
  const cell = document.createElement("th");
  cell.scope = "col";
  cell.textContent = column.label;
  cell.tabIndex = 0;
  const active = currentColumnSort();
  cell.classList.add("sortable-column");
  cell.title = "Click to sort. Right-click to choose a direction.";
  if (active?.key === column.key) {
    cell.setAttribute("aria-sort", active.direction === "desc" ? "descending" : "ascending");
    const mark = document.createElement("span");
    mark.className = "column-sort-mark";
    mark.textContent = sortMark(column.kind, active.direction);
    cell.append(mark);
  }
  const sort = () => {
    toggleColumnSort(column.key);
    if (sortMenu) sortMenu.hidden = true;
    renderTable();
  };
  cell.addEventListener("click", sort);
  cell.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    sort();
  });
  cell.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    openColumnSortMenu(column, event.clientX, event.clientY);
  });
  return cell;
}

function sortMark(kind, direction) {
  if (kind === "number") return direction === "desc" ? "9–0" : "0–9";
  return direction === "desc" ? "Z–A" : "A–Z";
}

let sortMenu = null;

function openColumnSortMenu(column, x, y) {
  const menu = ensureSortMenu();
  const dialMenu = document.getElementById("prospectMenu");
  if (dialMenu) dialMenu.hidden = true;
  const active = currentColumnSort();
  const key = column.key;
  menu.replaceChildren();
  const choices = column.kind === "number"
    ? [["asc", "Sort 0–9"], ["desc", "Sort 9–0"]]
    : [["asc", "Sort A–Z"], ["desc", "Sort Z–A"]];
  for (const [direction, text] of choices) {
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
  syncStateFilter();
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

  for (const column of LEAD_COLUMNS) head.append(headerCell(column));
  for (const column of extras) head.append(headerCell({ label: column, key: `field:${column}`, kind: "text" }));
  for (const column of TRAILING_COLUMNS) head.append(headerCell(column));
  appendLeadRows(body, leads, extras, renderTable);
  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV or add a prospect to start your workspace."
    : "Change the search or filters to see more rows.";
  byId("crmTable").hidden = state.leads.length === 0;
  const summary = `${leads.length} of ${state.leads.length} prospect${state.leads.length === 1 ? "" : "s"}`;
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}
