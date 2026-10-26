import { postJson, request } from "../../_core/api.js";
import { applyMutationPayload, loadAppState } from "../../_core/sync-state.js";
import { state } from "../../_core/state.js";
import { selectedLeadIds, selection } from "./selection.js";
import {
  CALLBACK_STATUS_HOURS,
  CRM_STATUS_KEYS,
  CRM_STATUS_LABELS,
  STATUS_LABELS,
  byId,
} from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../core.js";

export function bindProspects() {
  document.addEventListener("prospect-status", (event) => {
    const { lead, status, select } = event.detail;
    changeLeadStatus(lead, status, select);
  });
  document.addEventListener("prospect-field", (event) => {
    saveLeadField(event.detail);
  });
}

export async function changeLeadStatus(lead, status, select) {
  const next = String(status || "").trim();
  if (!CRM_STATUS_KEYS.includes(next)) {
    showToast(`Choose a valid call status (${next || "empty"}).`, true);
    select.value = lead.status || "new";
    return;
  }
  select.disabled = true;
  byId("saveState").textContent = "Saving…";
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, { status: next });
    await applyMutationPayload(result);
    byId("saveState").textContent = "All changes saved";
    render();
    const label = next === "call"
      ? `callback in ${CALLBACK_STATUS_HOURS} hours`
      : (CRM_STATUS_LABELS[next] || STATUS_LABELS[next] || next).toLowerCase();
    showToast(`${lead.name || lead.phone}: ${label}`);
  } catch (error) {
    select.value = lead.status || "new";
    select.disabled = false;
    byId("saveState").textContent = "Save failed";
    showToast(error.message, true);
  }
}

async function saveLeadField({ lead, field, value, previous, extra, input }) {
  const payload = extra ? { fields: { [extra]: value } } : { [field]: value };
  input.disabled = true;
  byId("saveState").textContent = "Saving…";
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/fields`, payload);
    await applyMutationPayload(result);
    byId("saveState").textContent = "All changes saved";
    input.blur();
    render();
  } catch (error) {
    if (input.isConnected) {
      input.value = previous;
      input.disabled = false;
    }
    byId("saveState").textContent = "Save failed";
    showToast(error.message, true);
  }
}

export async function deleteSelectedProspects() {
  const ids = [...selectedLeadIds];
  if (!ids.length) return;
  const noun = ids.length === 1 ? "prospect" : "prospects";
  if (!window.confirm(`Delete ${ids.length} selected ${noun}? This cannot be undone.`)) return;

  const button = byId("deleteSelectedButton");
  button.disabled = true;
  byId("saveState").textContent = "Deleting…";
  const results = await Promise.allSettled(ids.map((id) => request(`/api/leads/${encodeURIComponent(id)}`, { method: "DELETE" })));
  try {
    await loadAppState();
    const failed = results.filter((result) => result.status === "rejected");
    if (failed.length === 0) {
      selectedLeadIds.clear();
      selection.anchorId = null;
      byId("saveState").textContent = "All changes saved";
      render();
      showToast(`${ids.length} ${noun} deleted`);
    } else {
      byId("saveState").textContent = "Some deletions failed";
      render();
      showToast(`${ids.length - failed.length} deleted; ${failed.length} could not be deleted.`, true);
    }
  } catch (error) {
    byId("saveState").textContent = "Refresh failed";
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}
