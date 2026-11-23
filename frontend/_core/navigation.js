import { byId, setText } from "./format.js";
import { renderCallerPool, renderTable } from "./registry.js";
import { render } from "./render.js";
import { S } from "./state.js";
import { wireSetDashboardTab } from "./dashboard-tab.js";

/** Top chrome tabs: manual dialer, call log, CRM database. */
const TOP_NAV_TABS = ["dialer", "dials", "prospects"];

/** Hidden panels (caller pool) remain reachable for dialer renderers. */
const DASHBOARD_TABS = [...TOP_NAV_TABS, "pool"];

const TAB_ACTIVE_KEY = "prospect-desk-dashboard-tab";
/** Bumped when top tabs become Dialer · Call log · CRM (clears old workflow/pipeline selection). */
const TAB_LAYOUT_KEY = "godial-tab-layout-dialer-v1";
const TAB_BUTTONS = {
  dialer: "dialerTabButton",
  prospects: "prospectsTabButton",
  pool: "poolTabButton",
  dials: "dialsTabButton",
};
const TAB_TITLES = {
  dialer: "Dialer",
  prospects: "Global CRM",
  pool: "Caller pool",
  dials: "Call log",
};

function dashboardTabButtons() {
  return [...document.querySelectorAll(".app-top-tabs [data-dashboard-tab]")];
}

function savedDashboardTab() {
  try {
    if (!localStorage.getItem(TAB_LAYOUT_KEY)) {
      localStorage.setItem(TAB_LAYOUT_KEY, "1");
      localStorage.setItem(TAB_ACTIVE_KEY, "dialer");
      return "dialer";
    }
    const name = localStorage.getItem(TAB_ACTIVE_KEY) || "";
    if (TOP_NAV_TABS.includes(name)) return name;
    if (name && !TOP_NAV_TABS.includes(name)) {
      localStorage.setItem(TAB_ACTIVE_KEY, TOP_NAV_TABS[0]);
    }
    return TOP_NAV_TABS[0];
  } catch {
    return TOP_NAV_TABS[0];
  }
}

function rememberDashboardTab(name) {
  try {
    localStorage.setItem(TAB_ACTIVE_KEY, name);
  } catch {
    // ignore quota / private mode
  }
}

export function setDashboardTab(name, moveFocus = false) {
  S.dashboardTab = DASHBOARD_TABS.includes(name) ? name : TOP_NAV_TABS[0];
  rememberDashboardTab(S.dashboardTab);
  const selectedButton = byId(TAB_BUTTONS[S.dashboardTab]);
  for (const button of dashboardTabButtons()) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  const dialerPanel = byId("dialerTabPanel");
  if (dialerPanel) dialerPanel.hidden = S.dashboardTab !== "dialer";
  for (const tab of ["prospects", "pool", "dials"]) {
    const panel = byId(`${tab}TabPanel`);
    if (panel) panel.hidden = S.dashboardTab !== tab;
  }
  setText("pageTitle", TAB_TITLES[S.dashboardTab]);
  byId("crmView")?.classList.toggle("is-global-crm-view", S.dashboardTab === "prospects");
  if (S.dashboardTab === "prospects") renderTable();
  if (S.dashboardTab === "pool") renderCallerPool();
  render();
  if (S.dashboardTab === "dials") {
    import("../features/_dialer/dials.js").then((module) => module.refreshDialsTab());
  }
  if (moveFocus && selectedButton) selectedButton.focus();
}

export function bindNavigation() {
  for (const tabButton of dashboardTabButtons()) {
    tabButton.draggable = false;
    tabButton.addEventListener("click", () => setDashboardTab(tabButton.dataset.dashboardTab));
    tabButton.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      const tabs = dashboardTabButtons().map((button) => button.dataset.dashboardTab);
      const index = tabs.indexOf(tabButton.dataset.dashboardTab);
      const forward = event.key === "ArrowRight";
      const next = event.key === "Home" ? 0
        : event.key === "End" ? tabs.length - 1
          : (index + (forward ? 1 : tabs.length - 1)) % tabs.length;
      setDashboardTab(tabs[next], true);
    });
  }
  setDashboardTab(savedDashboardTab());
}

wireSetDashboardTab(setDashboardTab);