import { S, state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import { byId, setText } from "../../_core/format.js";
import { setDashboardTab } from "../../_core/dashboard-tab.js";
import { appendLeadRows } from "./rows.js";
import { LEAD_COLUMNS, TRAILING_COLUMNS, crmTableSignature, currentColumnSort, filteredLeads, importedColumns, setColumnSort, syncStateFilter, toggleColumnSort } from "./query.js";

const PAGE_SIZE = 50;
let visibleRowCount = PAGE_SIZE;
let lastCrmTableSignature = null;
let lastFilterSignature = null;
let loadMoreBound = false;

function crmPagingSignature(dataSignature = crmTableSignature()) {
  const payload = JSON.parse(dataSignature);
  return JSON.stringify({ filter: payload.filter, sort: payload.sort });
}

function tableRenderSignature(dataSignature = crmTableSignature()) {
  return `${dataSignature}\u0004${visibleRowCount}`;
}

function resetCrmTablePaging() {
  visibleRowCount = PAGE_SIZE;
}

function bindCrmLoadMore() {
  if (loadMoreBound) return;
  loadMoreBound = true;
  byId("crmTableLoadMore")?.addEventListener("click", () => {
    visibleRowCount += PAGE_SIZE;
    renderTable();
  });
}

bindCrmLoadMore();

/** Drop CRM table DOM when leaving Global CRM to free memory. */
export function releaseProspectsTableDom() {
  lastCrmTableSignature = null;
  lastFilterSignature = null;
  resetCrmTablePaging();
  byId("tableHead")?.replaceChildren();
  byId("tableBody")?.replaceChildren();
  const loadMore = byId("crmTableLoadMore");
  if (loadMore) loadMore.hidden = true;
}

export function focusProspect(leadId) {
  if (!leadId) return;
  setDashboardTab("prospects");
  queueMicrotask(() => {
    let row = document.querySelector(`#tableBody tr[data-lead-id="${leadId}"]`);
    if (!row) {
      const index = filteredLeads().findIndex((lead) => lead.id === leadId);
      if (index >= 0) {
        visibleRowCount = Math.max(visibleRowCount, index + 1);
        renderTable();
        row = document.querySelector(`#tableBody tr[data-lead-id="${leadId}"]`);
      }
    }
    if (!row) return;
    row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    row.classList.add("prospect-menu-target");
    setTimeout(() => row.classList.remove("prospect-menu-target"), 2000);
  });
}

export function renderTableIfStale() {
  if (fieldEditorFocused()) return;
  if (tableRenderSignature() !== lastCrmTableSignature) renderTable();
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
    resetCrmTablePaging();
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
      resetCrmTablePaging();
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
  if (!(active instanceof HTMLElement) || !byId("crmTable")?.contains(active)) return false;
  return active.classList.contains("cell-editor") || active.classList.contains("notes-editor");
}

export function renderTable() {
  if (S.dashboardTab !== "prospects") return;
  syncStateFilter();
  const dataSignature = crmTableSignature();
  const pagingSignature = crmPagingSignature(dataSignature);
  if (lastFilterSignature !== null && pagingSignature !== lastFilterSignature) {
    resetCrmTablePaging();
  }
  lastFilterSignature = pagingSignature;
  lastCrmTableSignature = tableRenderSignature(dataSignature);
  const head = byId("tableHead");
  const body = byId("tableBody");
  if (!head || !body) return;
  const leads = filteredLeads();
  const visibleLeads = leads.slice(0, visibleRowCount);
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
  const selectedVisibleCount = visibleLeads.filter((lead) => selectedLeadIds.has(lead.id)).length;
  selectAll.checked = visibleLeads.length > 0 && selectedVisibleCount === visibleLeads.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < visibleLeads.length;
  selectAll.addEventListener("change", () => {
    for (const lead of visibleLeads) {
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
  appendLeadRows(body, visibleLeads, extras, renderTable);
  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV or add a prospect to start your workspace."
    : "Change the search or filters to see more rows.";
  byId("crmTable").hidden = state.leads.length === 0;
  const showing = Math.min(visibleRowCount, leads.length);
  const matched = leads.length;
  const total = state.leads.length;
  let summary;
  if (matched === 0) {
    summary = `0 of ${total} prospect${total === 1 ? "" : "s"}`;
  } else if (showing < matched) {
    summary = `Showing ${showing} of ${matched} matching (${total} total)`;
  } else if (matched < total) {
    summary = `${matched} of ${total} prospect${total === 1 ? "" : "s"}`;
  } else {
    summary = `${total} prospect${total === 1 ? "" : "s"}`;
  }
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const loadMore = byId("crmTableLoadMore");
  if (loadMore) {
    const more = matched > showing;
    loadMore.hidden = !more || state.leads.length === 0;
    if (more) {
      const next = Math.min(PAGE_SIZE, matched - showing);
      loadMore.textContent = `Load ${next} more`;
    }
  }
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}
