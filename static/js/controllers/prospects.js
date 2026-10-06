import { postJson, request } from "../../_core/api.js";
import { S, selectedLeadIds, state } from "../../_core/state.js";
import { STATUS_LABELS, byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../views/render.js";

export function bindProspects() {
  document.addEventListener("prospect-status", (event) => {
    const { lead, status, select } = event.detail;
    changeLeadStatus(lead, status, select);
  });
}

export async function changeLeadStatus(lead, status, select) {
  select.disabled = true;
  byId("saveState").textContent = "Saving…";
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, { status });
    Object.assign(state, result.state);
    byId("saveState").textContent = "All changes saved";
    render();
    showToast(`${lead.name || lead.phone}: ${status === "call" ? "call scheduled for tomorrow" : STATUS_LABELS[status].toLowerCase()}`);
  } catch (error) {
    select.value = lead.status;
    select.disabled = false;
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
    Object.assign(state, await request("/api/state"));
    const failed = results.filter((result) => result.status === "rejected");
    if (failed.length === 0) {
      selectedLeadIds.clear();
      S.selectionAnchorId = null;
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
