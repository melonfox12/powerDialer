import { S } from "../../_core/state.js";
import { request, postJson } from "../../_core/api.js";
import { buildAdjacentChainEdges } from "./transitions.js";
import {
  clearWorkflowSelection,
  getWorkflowSelection,
  setWorkflowSelection,
} from "./selection.js";
import { activeCampaignId, applyCampaignCatalog } from "./campaign-chrome.js";
import { renderWorkflowNodeView } from "./node-view.js";

<<<<<<< HEAD:misc/frontend-workflow-pipeline/_workflow/workflow-url.js
const DASHBOARD_TABS = ["prospects", "workflow", "pipeline"];
=======
const DASHBOARD_TABS = [
  "prospects",
  "workflow",
  "pipeline",
  "dialer",
  "aiDialerAgent",
  "performance",
  "pool",
  "dials",
];
>>>>>>> 1f6194cd2ae87ec7fff49dab3cbd173c490ead53:static/features/_workflow/workflow-url.js

const PARAM_TAB = "tab";
const PARAM_CAMPAIGN = "campaign";
const PARAM_NODE = "wfNode";
const PARAM_EDGE = "wfEdge";
const PARAM_LEAD = "wfLead";
const PARAM_VIA = "wfVia";
const PARAM_CTX = "wfCtx";
const PARAM_VIEW = "wfView";
const VIEW_KEY = "godial-workflow-node-view-mode";

let applyingFromUrl = false;
let bound = false;

export function readTabFromUrl() {
  try {
    const tab = new URLSearchParams(window.location.search).get(PARAM_TAB);
    if (tab && DASHBOARD_TABS.includes(tab)) return tab;
  } catch {
    // ignore
  }
  return null;
}

function edgeById(edgeId) {
  return buildAdjacentChainEdges().find((row) => row.id === edgeId) || null;
}

function selectionFromParams(params) {
  const leadId = params.get(PARAM_LEAD);
  if (leadId) {
    const via = params.get(PARAM_VIA) === "edge" ? "edge" : "node";
    const contextId = params.get(PARAM_CTX) || "";
    if (contextId) return { type: "lead", leadId, via, contextId };
  }
  const edgeId = params.get(PARAM_EDGE);
  if (edgeId) {
    const edge = edgeById(edgeId);
    if (edge) return { type: "edge", edgeId: edge.id, from: edge.from, to: edge.to };
  }
  const nodeId = params.get(PARAM_NODE);
  if (nodeId) return { type: "node", nodeId };
  return null;
}

function paramsFromSelection(sel) {
  const patch = {
    [PARAM_NODE]: null,
    [PARAM_EDGE]: null,
    [PARAM_LEAD]: null,
    [PARAM_VIA]: null,
    [PARAM_CTX]: null,
  };
  if (!sel) return patch;
  if (sel.type === "node") patch[PARAM_NODE] = sel.nodeId;
  if (sel.type === "edge") patch[PARAM_EDGE] = sel.edgeId;
  if (sel.type === "lead") {
    patch[PARAM_LEAD] = sel.leadId;
    patch[PARAM_VIA] = sel.via;
    patch[PARAM_CTX] = sel.contextId;
  }
  return patch;
}

function memberViewFromUrl(params) {
  const view = params.get(PARAM_VIEW);
  return view === "kanban" ? "kanban" : view === "list" ? "list" : null;
}

function applyMemberViewFromUrl(params) {
  const view = memberViewFromUrl(params);
  if (!view) return;
  try {
    localStorage.setItem(VIEW_KEY, view);
  } catch {
    // ignore
  }
}

function buildUrlSearch(extra = {}) {
  const url = new URL(window.location.href);
  const tab = S.dashboardTab;
  if (tab && DASHBOARD_TABS.includes(tab)) url.searchParams.set(PARAM_TAB, tab);
  const campaign = activeCampaignId();
  if (campaign) url.searchParams.set(PARAM_CAMPAIGN, campaign);
  else url.searchParams.delete(PARAM_CAMPAIGN);

  const selPatch = paramsFromSelection(getWorkflowSelection());
  const keys = [PARAM_NODE, PARAM_EDGE, PARAM_LEAD, PARAM_VIA, PARAM_CTX];
  for (const key of keys) {
    const value = extra[key] ?? selPatch[key];
    if (value) url.searchParams.set(key, value);
    else url.searchParams.delete(key);
  }

  let view = null;
  try {
    view = localStorage.getItem(VIEW_KEY);
  } catch {
    // ignore
  }
  if (view === "kanban" || view === "list") url.searchParams.set(PARAM_VIEW, view);
  else url.searchParams.delete(PARAM_VIEW);

  return url.pathname + url.search;
}

export function syncWorkflowUrlToLocation({ push = false } = {}) {
  if (applyingFromUrl) return;
  const path = buildUrlSearch();
  const current = window.location.pathname + window.location.search;
  if (path === current) return;
  if (push) history.pushState({ workflowUrl: true }, "", path);
  else history.replaceState({ workflowUrl: true }, "", path);
}

export async function applyWorkflowStateFromUrl() {
  const params = new URLSearchParams(window.location.search);
  const workflowVisible = !document.getElementById("workflowTabPanel")?.hidden;
  applyingFromUrl = true;
  try {
    applyMemberViewFromUrl(params);
    const campaignId = params.get(PARAM_CAMPAIGN);
    if (campaignId && activeCampaignId() !== campaignId) {
      const catalog = await request("/api/campaigns");
      const known = (catalog.campaigns || []).some((row) => row.id === campaignId);
      if (known) {
        const next = await postJson("/api/campaigns/active", { id: campaignId });
        applyCampaignCatalog(next);
        const { refreshCampaignFlow } = await import("./campaign-flow.js");
        const { refreshCampaignStats } = await import("./campaign-stats.js");
        await refreshCampaignFlow();
        await refreshCampaignStats();
      }
    }
    if (workflowVisible) {
      const sel = selectionFromParams(params);
      if (sel) setWorkflowSelection(sel);
      else clearWorkflowSelection();
      renderWorkflowNodeView();
    }
    syncWorkflowUrlToLocation();
  } finally {
    applyingFromUrl = false;
  }
}

export function bindWorkflowUrl() {
  if (bound) return;
  bound = true;
  window.addEventListener("popstate", () => {
    const tab = readTabFromUrl();
    if (tab) {
      void import("../../_core/dashboard-tab.js").then(({ setDashboardTab }) => setDashboardTab(tab));
    }
    void applyWorkflowStateFromUrl();
  });
  window.addEventListener("godial-workflow-selection", () => {
    syncWorkflowUrlToLocation({ push: true });
  });
}