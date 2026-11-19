import { registerRenderer } from "../../_core/registry.js";
import { request } from "../../_core/api.js";
import { activeCampaignId } from "./campaign-chrome.js";

/** @type {{ revision: number, nodes: Record<string, { count: number }>, edges: Record<string, { count: number }> } | null} */
let snapshot = null;

export function getCampaignFlowSnapshot() {
  return snapshot;
}

export function nodeLeadCount(nodeId) {
  return snapshot?.nodes?.[nodeId]?.count ?? 0;
}

export function edgeLeadCount(edgeId) {
  return snapshot?.edges?.[edgeId]?.count ?? 0;
}

export async function refreshCampaignFlow() {
  if (document.getElementById("workflowTabPanel")?.hidden) return snapshot;
  const campaignId = activeCampaignId();
  if (!campaignId) {
    snapshot = null;
    return snapshot;
  }
  try {
    snapshot = await request(`/api/campaigns/${encodeURIComponent(campaignId)}/flow`);
    window.dispatchEvent(new CustomEvent("godial-workflow-flow"));
    return snapshot;
  } catch {
    snapshot = null;
    return snapshot;
  }
}

export function bindCampaignFlow() {
  registerRenderer(refreshCampaignFlow, "end", "workflow");
}