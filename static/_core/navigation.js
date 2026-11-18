import { byId, humanDialerPanel, setText } from "./format.js";
import { renderCallerPool, renderTable } from "./registry.js";
import { render } from "./render.js";
import { S } from "./state.js";

/** Tabs shown in the top chrome (fixed order). */
const TOP_NAV_TABS = ["prospects", "workflow", "pipeline"];

/** All dashboard panels; reachable via `setDashboardTab` even when not in the top bar. */
const DASHBOARD_TABS = [
  ...TOP_NAV_TABS,
  "dialer",
  "aiDialerAgent",
  "performance",
  "pool",
  "dials",
];
const TAB_ACTIVE_KEY = "prospect-desk-dashboard-tab";
const TAB_BUTTONS = {
  dialer: "dialerTabButton",
  aiDialerAgent: "aiDialerAgentTabButton",
  performance: "performanceTabButton",
  pipeline: "pipelineTabButton",
  workflow: "workflowTabButton",
  prospects: "prospectsTabButton",
  pool: "poolTabButton",
  dials: "dialsTabButton",
};
const TAB_TITLES = {
  dialer: "Dialer",
  aiDialerAgent: "AI Dialer Agent",
  performance: "Performance",
  pipeline: "Pipeline",
  workflow: "Workflow",
  prospects: "Global CRM",
  pool: "Caller pool",
  dials: "Total dials",
};

/** Fixed top bar order: Global CRM → Workflow → Pipeline (rightmost). */
export function normalizeTabOrder() {
  return [...TOP_NAV_TABS];
}

function topTabList() {
  return document.querySelector(".app-top-tabs");
}

function dashboardTabButtons() {
  return [...document.querySelectorAll(".app-top-tabs [data-dashboard-tab]")];
}

function tabButtonsByName() {
  return Object.fromEntries(dashboardTabButtons().map((button) => [button.dataset.dashboardTab, button]));
}

function applyTopTabOrder() {
  const list = topTabList();
  if (!list) return;
  const buttons = tabButtonsByName();
  for (const name of TOP_NAV_TABS) {
    if (buttons[name]) list.append(buttons[name]);
  }
}

function savedDashboardTab() {
  try {
    const name = localStorage.getItem(TAB_ACTIVE_KEY) || "";
    if (TOP_NAV_TABS.includes(name)) return name;
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

/** Match Performance column height to Dialer: document top → Recent activity row (+ doc bottom padding). */
export function syncPerformanceDocumentHeight() {
  const perf = document.querySelector(".performance-document");
  const panel = humanDialerPanel();
  const doc = panel?.querySelector(".dialer-document");
  const recent = doc?.querySelector(".activity-log-disclosure summary");
  if (!perf || !doc || !recent) return;

  const measure = () => {
    const docRect = doc.getBoundingClientRect();
    const recentRect = recent.getBoundingClientRect();
    if (!recentRect.height) return null;
    const padBottom = Number.parseFloat(getComputedStyle(doc).paddingBottom) || 0;
    return Math.round(recentRect.bottom - docRect.top + padBottom);
  };

  let height = measure();
  if (height == null && panel.hidden) {
    const restore = panel.hidden;
    panel.hidden = false;
    height = measure();
    panel.hidden = restore;
  }
  if (height != null && height > 0) {
    document.documentElement.style.setProperty("--performance-run-height", `${height}px`);
  }
}

function bindTabReorder() {
  applyTopTabOrder();
}

export function setDashboardTab(name, moveFocus = false) {
  S.dashboardTab = DASHBOARD_TABS.includes(name) ? name : TOP_NAV_TABS[0];
  rememberDashboardTab(S.dashboardTab);
  syncPerformanceDocumentHeight();
  const selectedButton = byId(TAB_BUTTONS[S.dashboardTab]);
  for (const button of dashboardTabButtons()) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  byId("dialerTabPanel").hidden = S.dashboardTab !== "dialer";
  byId("aiDialerAgentTabPanel").hidden = S.dashboardTab !== "aiDialerAgent";
  byId("metricsPanel").hidden = S.dashboardTab !== "performance";
  for (const tab of ["performance", "pipeline", "workflow", "prospects", "pool", "dials"]) {
    byId(`${tab}TabPanel`).hidden = S.dashboardTab !== tab;
  }
  setText("pageTitle", TAB_TITLES[S.dashboardTab]);
  byId("crmView")?.classList.toggle("is-workflow-view", S.dashboardTab === "workflow");
  byId("crmView")?.classList.toggle("is-global-crm-view", S.dashboardTab === "prospects");
  byId("crmView")?.classList.toggle("is-pipeline-view", S.dashboardTab === "pipeline");
  if (S.dashboardTab === "performance") {
    S.performanceFetchedAt = 0;
    S.performancePainted = null;
  }
  if (S.dashboardTab === "prospects") renderTable();
  if (S.dashboardTab === "pool") renderCallerPool();
  render();
  if (S.dashboardTab === "dials") {
    import("../features/_dialer/dials.js").then((module) => module.refreshDialsTab());
  }
  if (S.dashboardTab === "pipeline") {
    import("../features/pipeline.js").then((module) => {
      module.renderPipelineEditor();
      module.renderPipelineBoardAndRemember();
    });
  }
  if (S.dashboardTab === "workflow") {
    import("../features/workflow.js").then((module) => module.initWorkflowTab());
  }
  if (S.dashboardTab === "performance") {
    import("../features/performance.js").then((module) => module.repaintPerformanceChart());
  }
  if (moveFocus && selectedButton) selectedButton.focus();
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
  setPerformanceMode(S.performanceMode);
  bindTabReorder();
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
  for (const modeButton of document.querySelectorAll("[data-performance-mode]")) {
    modeButton.addEventListener("click", () => setPerformanceMode(modeButton.dataset.performanceMode));
  }
  window.addEventListener("resize", syncPerformanceDocumentHeight);
  setDashboardTab(savedDashboardTab());
  requestAnimationFrame(() => {
    syncPerformanceDocumentHeight();
  });
}