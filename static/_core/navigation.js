import { byId, setText } from "./format.js";
import { renderCallerPool, renderTable } from "./registry.js";
import { S } from "./state.js";

const DASHBOARD_TABS = ["dialer", "performance", "prospects", "pool"];
const TAB_ORDER_KEY = "prospect-desk-sidebar-order";
const TAB_BUTTONS = {
  dialer: "dialerTabButton",
  performance: "performanceTabButton",
  prospects: "prospectsTabButton",
  pool: "poolTabButton",
};
const TAB_TITLES = { dialer: "Dialer", performance: "Performance", prospects: "Prospects", pool: "Caller pool" };

export function normalizeTabOrder(order) {
  const next = [];
  for (const name of order || []) {
    if (DASHBOARD_TABS.includes(name) && !next.includes(name)) next.push(name);
  }
  for (const name of DASHBOARD_TABS) {
    if (!next.includes(name)) next.push(name);
  }
  return next;
}

function sidebarTabs() {
  return [...document.querySelectorAll(".side-links [data-dashboard-tab]")];
}

function applyTabOrder(order) {
  const list = document.querySelector(".side-links");
  if (!list) return;
  const buttons = Object.fromEntries(sidebarTabs().map((button) => [button.dataset.dashboardTab, button]));
  for (const name of normalizeTabOrder(order)) list.append(buttons[name]);
}

function savedTabOrder() {
  try {
    return normalizeTabOrder(JSON.parse(localStorage.getItem(TAB_ORDER_KEY) || "[]"));
  } catch {
    return [...DASHBOARD_TABS];
  }
}

function rememberTabOrder() {
  localStorage.setItem(TAB_ORDER_KEY, JSON.stringify(sidebarTabs().map((button) => button.dataset.dashboardTab)));
}

function placeTab(button, target, before) {
  const list = button.parentElement;
  if (before) list.insertBefore(button, target);
  else list.insertBefore(button, target.nextSibling);
  rememberTabOrder();
}

function clearDropMarks() {
  for (const button of sidebarTabs()) button.classList.remove("is-dragging", "is-drop-before", "is-drop-after");
}

function bindTabReorder() {
  applyTabOrder(savedTabOrder());
  let dragged = null;

  const markDrop = (button, clientY) => {
    for (const item of sidebarTabs()) item.classList.remove("is-drop-before", "is-drop-after");
    if (!button || button === dragged) return null;
    const rect = button.getBoundingClientRect();
    const before = clientY < rect.top + rect.height / 2;
    button.classList.add(before ? "is-drop-before" : "is-drop-after");
    return before;
  };

  document.addEventListener("dragover", (event) => {
    if (!dragged) return;
    event.preventDefault();
    const under = event.target.closest?.("[data-dashboard-tab]");
    markDrop(under, event.clientY);
  });

  for (const button of sidebarTabs()) {
    button.draggable = true;
    button.addEventListener("dragstart", (event) => {
      dragged = button;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", button.dataset.dashboardTab);
      button.classList.add("is-dragging");
    });
    button.addEventListener("dragover", (event) => {
      if (!dragged || dragged === button) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      markDrop(button, event.clientY);
    });
    button.addEventListener("drop", (event) => {
      event.preventDefault();
      const source = sidebarTabs().find((item) => item.dataset.dashboardTab === event.dataTransfer.getData("text/plain"));
      if (!source || source === button) return;
      const before = event.clientY < button.getBoundingClientRect().top + button.offsetHeight / 2;
      placeTab(source, button, before);
    });
    button.addEventListener("dragend", () => {
      dragged = null;
      clearDropMarks();
    });
  }
}

export function setDashboardTab(name, moveFocus = false) {
  S.dashboardTab = DASHBOARD_TABS.includes(name) ? name : "dialer";
  const selectedButton = byId(TAB_BUTTONS[S.dashboardTab]);
  for (const button of document.querySelectorAll("[data-dashboard-tab]")) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  byId("dialerTabPanel").hidden = S.dashboardTab !== "dialer";
  byId("metricsPanel").hidden = S.dashboardTab === "dialer";
  for (const tab of ["performance", "prospects", "pool"]) byId(`${tab}TabPanel`).hidden = S.dashboardTab !== tab;
  setText("pageTitle", TAB_TITLES[S.dashboardTab]);
  if (S.dashboardTab === "prospects") renderTable();
  if (S.dashboardTab === "pool") renderCallerPool();
  if (moveFocus) selectedButton.focus();
}

export function setPerformanceMode(mode) {
  S.performanceMode = mode === "all" ? "all" : "summary";
  byId("performanceTabPanel").dataset.mode = S.performanceMode;
  for (const button of document.querySelectorAll("[data-performance-mode]")) {
    const selected = button.dataset.performanceMode === S.performanceMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

export function bindNavigation() {
  bindTabReorder();
  for (const tabButton of sidebarTabs()) {
    tabButton.title = "Drag to reorder";
    tabButton.addEventListener("click", () => setDashboardTab(tabButton.dataset.dashboardTab));
    tabButton.addEventListener("keydown", (event) => {
      if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
        event.preventDefault();
        const tabs = sidebarTabs();
        const index = tabs.indexOf(tabButton);
        const sibling = tabs[index + (event.key === "ArrowUp" ? -1 : 1)];
        if (sibling) placeTab(tabButton, sibling, event.key === "ArrowUp");
        tabButton.focus();
        return;
      }
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = sidebarTabs().map((button) => button.dataset.dashboardTab);
      const index = tabs.indexOf(tabButton.dataset.dashboardTab);
      const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
      const next = event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1
          : (index + (forward ? 1 : tabs.length - 1)) % tabs.length;
      setDashboardTab(tabs[next], true);
    });
  }
  for (const modeButton of document.querySelectorAll("[data-performance-mode]")) {
    modeButton.addEventListener("click", () => setPerformanceMode(modeButton.dataset.performanceMode));
  }
}
