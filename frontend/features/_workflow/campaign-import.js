import { postJson } from "../../_core/api.js";
import { showToast } from "../../_core/notify.js";
import { activeCampaignId, applyCampaignCatalog, refreshCampaignCatalog } from "./campaign-chrome.js";
import { refreshCampaignFlow } from "./campaign-flow.js";

/** @type {{ leadIds: string[], preview: object | null }} */
let pendingImport = { leadIds: [], preview: null };

function dialogEl() {
  return document.getElementById("workflowCampaignImportDialog");
}

function summaryEl() {
  return document.getElementById("workflowCampaignImportSummary");
}

function warningsEl() {
  return document.getElementById("workflowCampaignImportWarnings");
}

function confirmBtn() {
  return document.getElementById("workflowCampaignImportConfirm");
}

function renderPreview(preview) {
  const summary = summaryEl();
  const warnings = warningsEl();
  const confirm = confirmBtn();
  if (!summary || !warnings || !confirm) return;
  const newCount = preview?.new_count ?? 0;
  const requested = preview?.requested ?? pendingImport.leadIds.length;
  summary.textContent =
    newCount > 0
      ? `${newCount} new prospect${newCount === 1 ? "" : "s"} will join this campaign (${requested} selected).`
      : `None of the ${requested} selected prospect${requested === 1 ? "" : "s"} can be added.`;
  warnings.replaceChildren();
  for (const item of preview?.warnings || []) {
    const line = document.createElement("li");
    line.className = "workflow-import-warning";
    const sample = Array.isArray(item.lead_ids) && item.lead_ids.length ? ` (e.g. ${item.lead_ids.slice(0, 3).join(", ")})` : "";
    line.textContent = `${item.count} · ${item.message || item.code}${sample}`;
    warnings.append(line);
  }
  const wrap = warnings.closest(".workflow-import-warnings-wrap");
  if (wrap) wrap.hidden = !(preview?.warnings || []).length;
  confirm.disabled = newCount <= 0;
  confirm.textContent = newCount > 0 ? `Import ${newCount}` : "Nothing to import";
}

export async function openCampaignImportDialog(leadIds) {
  const ids = [...new Set((leadIds || []).map((id) => String(id || "").trim()).filter(Boolean))];
  if (!ids.length) return;
  const campaignId = activeCampaignId();
  if (!campaignId) {
    showToast("Create or select a campaign first.", true);
    return;
  }
  const dialog = dialogEl();
  if (!dialog) return;
  pendingImport = { leadIds: ids, preview: null };
  try {
    const preview = await postJson(`/api/campaigns/${encodeURIComponent(campaignId)}/import/preview`, {
      lead_ids: ids,
    });
    pendingImport.preview = preview;
    renderPreview(preview);
    if (typeof dialog.showModal === "function") dialog.showModal();
  } catch (error) {
    showToast(error.message, true);
  }
}

async function confirmImport() {
  const campaignId = activeCampaignId();
  const dialog = dialogEl();
  if (!campaignId || !pendingImport.leadIds.length) return;
  const confirm = confirmBtn();
  if (confirm) confirm.disabled = true;
  try {
    const result = await postJson(`/api/campaigns/${encodeURIComponent(campaignId)}/import`, {
      lead_ids: pendingImport.leadIds,
    });
    if (result.catalog) applyCampaignCatalog(result.catalog);
    else await refreshCampaignCatalog();
    await refreshCampaignFlow();
    const added = result.added ?? 0;
    showToast(added ? `Imported ${added} prospect${added === 1 ? "" : "s"} into the campaign.` : "No new prospects were imported.");
    dialog?.close();
    pendingImport = { leadIds: [], preview: null };
  } catch (error) {
    showToast(error.message, true);
    if (confirm) confirm.disabled = false;
  }
}

let bound = false;

export function bindCampaignImportDialog() {
  if (bound) return;
  bound = true;
  document.getElementById("workflowCampaignImportCancel")?.addEventListener("click", () => {
    dialogEl()?.close();
    pendingImport = { leadIds: [], preview: null };
  });
  document.getElementById("workflowCampaignImportConfirm")?.addEventListener("click", () => {
    void confirmImport();
  });
  dialogEl()?.addEventListener("cancel", () => {
    pendingImport = { leadIds: [], preview: null };
  });
}