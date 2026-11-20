import { byId, setText } from "./format.js";
import { renderTable } from "./registry.js";
import { render } from "./render.js";
import {
  ensureFullLeadsCatalog,
  maybeReleaseFullLeadsCatalog,
  needsFullLeadsCatalog,
} from "./sync-state.js";
import { wireSetDashboardTab } from "./dashboard-tab.js";
import { S } from "./state.js";
import { readTabFromUrl, syncWorkflowUrlToLocation } from "../features/_workflow/workflow-url.js";

/** Loaded on demand so navigation does not import feature modules that re-import `core.js` (cycle breaks tab binds). */
function releaseProspectsTableDomIfLoaded() {
  return import("../features/_prospects/table.js").then((module) => module.releaseProspectsTableDom());
}

function releaseWorkflowCrmSidebarDomIfLoaded() {
  return import("../features/_workflow/campaign-crm-sidebar.js").then((module) => module.releaseWorkflowCrmSidebarDom());
}

function releasePipelineBoardDomIfLoaded() {
  return import("../features/_pipeline/board.js").then((module) => module.releasePipelineBoardDom());
}

/** Drop heavy in-memory CRM catalog when the active tab only needs the slim summary. */
function releaseFullLeadsCatalogIfIdle() {
  if (needsFullLeadsCatalog()) return;
  void maybeReleaseFullLeadsCatalog(S.dashboardTab);
}

const DASHBOARD_TABS = ["prospects", "workflow", "pipeline"];
const TAB_ACTIVE_KEY = "prospect-desk-dashboard-tab";
const TAB_BUTTONS = {
  pipeline: "pipelineTabButton",
  workflow: "workflowTabButton",
  prospects: "prospectsTabButton",
};
const TAB_TITLES = {
  pipeline: "Pipeline",
  workflow: "Workflow",
  prospects: "Global CRM",
};

function dashboardTabButtons() {
  return [...document.querySelectorAll(".app-top-tabs [data-dashboard-tab]")];
}

function savedDashboardTab() {
  try {
    const name = localStorage.getItem(TAB_ACTIVE_KEY) || "";
    if (DASHBOARD_TABS.includes(name)) return name;
    return DASHBOARD_TABS[0];
  } catch {
    return DASHBOARD_TABS[0];
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
  const previousTab = S.dashboardTab;
  S.dashboardTab = DASHBOARD_TABS.includes(name) ? name : DASHBOARD_TABS[0];
  rememberDashboardTab(S.dashboardTab);
  if (previousTab === "prospects" && S.dashboardTab !== "prospects") {
    void releaseProspectsTableDomIfLoaded();
  }
  if (previousTab === "workflow" && S.dashboardTab !== "workflow") {
    void releaseWorkflowCrmSidebarDomIfLoaded();
  }
  if (previousTab === "pipeline" && S.dashboardTab !== "pipeline") {
    void releasePipelineBoardDomIfLoaded();
  }
  if (previousTab !== S.dashboardTab) {
    releaseFullLeadsCatalogIfIdle();
  }
  const selectedButton = byId(TAB_BUTTONS[S.dashboardTab]);
  for (const button of dashboardTabButtons()) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  for (const tab of DASHBOARD_TABS) {
    const panel = byId(`${tab}TabPanel`);
    if (panel) panel.hidden = S.dashboardTab !== tab;
  }
  setText("pageTitle", TAB_TITLES[S.dashboardTab]);
  byId("crmView")?.classList.toggle("is-workflow-view", S.dashboardTab === "workflow");
  byId("crmView")?.classList.toggle("is-global-crm-view", S.dashboardTab === "prospects");
  byId("crmView")?.classList.toggle("is-pipeline-view", S.dashboardTab === "pipeline");
  render();
  if (S.dashboardTab === "prospects") {
    ensureFullLeadsCatalog().then(() => {
      if (S.dashboardTab === "prospects") renderTable();
    });
  }
  if (S.dashboardTab === "pipeline") {
    ensureFullLeadsCatalog().then(() => {
      if (S.dashboardTab !== "pipeline") return;
      import("../features/pipeline.js").then((module) => {
        if (S.dashboardTab !== "pipeline") return;
        module.renderPipelineEditor();
        module.renderPipelineBoardAndRemember();
      });
    });
  }
  if (S.dashboardTab === "workflow") {
    import("../features/workflow.js").then((module) => module.initWorkflowTab());
  }
  if (moveFocus && selectedButton) selectedButton.focus();
  syncWorkflowUrlToLocation();
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
  setDashboardTab(readTabFromUrl() || savedDashboardTab());
}

wireSetDashboardTab(setDashboardTab);