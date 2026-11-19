import { registerRenderer } from "../../_core/registry.js";
import { request, postJson } from "../../_core/api.js";
import { setText } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";

/** @type {{ revision: number, active_id: string | null, campaigns: Array<{ id: string, name: string, status: string, member_count: number }> }} */
let catalog = { revision: 0, active_id: null, campaigns: [] };

let bound = false;

export function activeCampaignId() {
  const select = document.getElementById("workflowCampaignSelect");
  const value = select?.value || catalog.active_id;
  return value || catalog.campaigns[0]?.id || null;
}

export function activeCampaign() {
  const id = activeCampaignId();
  return catalog.campaigns.find((row) => row.id === id) || null;
}

export function getCampaignCatalog() {
  return catalog;
}

export function applyCampaignCatalog(next) {
  if (next) catalog = next;
  renderCampaignToolbar();
}

export async function refreshCampaignCatalog() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  try {
    catalog = await request("/api/campaigns");
    renderCampaignToolbar();
    const { refreshCampaignFlow } = await import("./campaign-flow.js");
    const { refreshCampaignStats } = await import("./campaign-stats.js");
    await refreshCampaignFlow();
    await refreshCampaignStats();
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderCampaignToolbar() {
  const select = document.getElementById("workflowCampaignSelect");
  if (!select) return;
  const previous = select.value || catalog.active_id || "";
  select.disabled = false;
  select.replaceChildren();
  for (const row of catalog.campaigns || []) {
    const option = document.createElement("option");
    option.value = row.id;
    const statusLabel = row.status === "draft" ? "Draft" : row.status;
    option.textContent = `${row.name} — ${statusLabel} · ${row.member_count} in campaign`;
    select.append(option);
  }
  const next = catalog.campaigns.some((row) => row.id === previous)
    ? previous
    : catalog.active_id || catalog.campaigns[0]?.id || "";
  if (next) select.value = next;
  paintCampaignMemberCount();
}

function paintCampaignMemberCount() {
  const campaign = activeCampaign();
  const count = campaign?.member_count ?? 0;
  setText("workflowCampaignMemberCount", String(count));
}

async function setActiveCampaign(campaignId) {
  if (!campaignId) return;
  try {
    catalog = await postJson("/api/campaigns/active", { id: campaignId });
    renderCampaignToolbar();
    const { refreshCampaignFlow } = await import("./campaign-flow.js");
    const { refreshCampaignStats } = await import("./campaign-stats.js");
    await refreshCampaignFlow();
    await refreshCampaignStats();
  } catch (error) {
    showToast(error.message, true);
    await refreshCampaignCatalog();
  }
}

async function createCampaign() {
  const name = window.prompt("Campaign name", `Campaign ${(catalog.campaigns?.length || 0) + 1}`);
  if (name == null) return;
  try {
    catalog = await postJson("/api/campaigns", { name: name.trim() });
    const created = catalog.campaigns[catalog.campaigns.length - 1];
    if (created?.id) await setActiveCampaign(created.id);
    else renderCampaignToolbar();
    showToast("Campaign created.");
  } catch (error) {
    showToast(error.message, true);
  }
}

export function bindCampaignChrome() {
  if (bound) return;
  bound = true;
  document.getElementById("workflowCampaignSelect")?.addEventListener("change", (event) => {
    void setActiveCampaign(event.target.value);
  });
  document.getElementById("workflowCampaignCreateBtn")?.addEventListener("click", () => {
    void createCampaign();
  });
  registerRenderer(refreshCampaignCatalog, "end", "workflow");
}