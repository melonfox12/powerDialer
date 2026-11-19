import { registerRenderer } from "../../_core/registry.js";
import { request } from "../../_core/api.js";
import { activeCampaignId } from "./campaign-chrome.js";
import {
  canvasEdgeLeadIds,
  edgeLeadCount,
  getFlowSnapshot,
  nodeLeadCount,
  nodeLeadIds,
  setFlowSnapshot,
} from "./flow-snapshot.js";

export {
  canvasEdgeLeadIds,
  edgeLeadCount,
  nodeLeadCount,
  nodeLeadIds,
};

export function getCampaignFlowSnapshot() {
  return getFlowSnapshot();
}

function workflowCanvasInteracting() {
  const view = document.getElementById("workflowViewport");
  return Boolean(view?.classList.contains("is-workflow-interacting") || view?.classList.contains("is-panning"));
}

export async function refreshCampaignFlow() {
  if (document.getElementById("workflowTabPanel")?.hidden) return getFlowSnapshot();
  if (workflowCanvasInteracting()) return getFlowSnapshot();
  const campaignId = activeCampaignId();
  if (!campaignId) {
    setFlowSnapshot(null);
    return null;
  }
  try {
    const next = await request(`/api/campaigns/${encodeURIComponent(campaignId)}/flow`);
    setFlowSnapshot(next);
    if (!workflowCanvasInteracting()) {
      window.dispatchEvent(new CustomEvent("godial-workflow-flow"));
    }
    return next;
  } catch {
    setFlowSnapshot(null);
    return null;
  }
}

export function bindCampaignFlow() {
  registerRenderer(refreshCampaignFlow, "end", "workflow");
}