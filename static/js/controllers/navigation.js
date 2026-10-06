import { S } from "../../_core/state.js";
import { byId, setText } from "../../_core/format.js";
import { renderCallerPool, renderTable } from "../../core.js";

export function setDashboardTab(name, moveFocus = false) {
  const tabs = ["dialer", "performance", "prospects", "pool"];
  S.dashboardTab = tabs.includes(name) ? name : "dialer";
  const tabButtons = {
    dialer: "dialerTabButton",
    performance: "performanceTabButton",
    prospects: "prospectsTabButton",
    pool: "poolTabButton",
  };
  const titles = { dialer: "Dialer", performance: "Performance", prospects: "Prospects", pool: "Caller pool" };
  const selectedButton = byId(tabButtons[S.dashboardTab]);
  for (const button of document.querySelectorAll("[data-dashboard-tab]")) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  byId("dialerTabPanel").hidden = S.dashboardTab !== "dialer";
  byId("metricsPanel").hidden = S.dashboardTab === "dialer";
  for (const tab of ["performance", "prospects", "pool"]) byId(`${tab}TabPanel`).hidden = S.dashboardTab !== tab;
  setText("pageTitle", titles[S.dashboardTab]);
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
  for (const tabButton of document.querySelectorAll("[data-dashboard-tab]")) {
    tabButton.addEventListener("click", () => setDashboardTab(tabButton.dataset.dashboardTab));
    tabButton.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = ["dialer", "performance", "prospects", "pool"];
      const index = tabs.indexOf(tabButton.dataset.dashboardTab);
      const forward = event.key === "ArrowRight" || event.key === "ArrowDown";
      const next = event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1
          : (index + (forward ? 1 : tabs.length - 1)) % tabs.length;
      const name = tabs[next];
      setDashboardTab(name, true);
    });
  }
  for (const modeButton of document.querySelectorAll("[data-performance-mode]")) {
    modeButton.addEventListener("click", () => setPerformanceMode(modeButton.dataset.performanceMode));
  }
}
