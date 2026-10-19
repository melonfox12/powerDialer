import { postJson, request } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../core.js";
import { nextProspectLabel, queueProspect } from "./queue.js";

export function bindPreviewActions() {
  byId("skipNextButton").addEventListener("click", skipNextProspect);
  byId("removeNextButton").addEventListener("click", removeNextProspect);
}

async function skipNextProspect() {
  const lead = queueProspect();
  if (!lead) return;
  const button = byId("skipNextButton");
  button.disabled = true;
  try {
    Object.assign(state, await postJson("/api/next/skip", { id: lead.id }));
    showToast(`Skipped ${nextProspectLabel(lead)}`);
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = !queueProspect();
  }
}

async function removeNextProspect() {
  const lead = state.next_lead;
  if (!lead || state.running) return;
  const label = nextProspectLabel(lead);
  if (!window.confirm(`Remove ${label} from the CRM? This cannot be undone.`)) return;
  const button = byId("removeNextButton");
  button.disabled = true;
  try {
    Object.assign(state, await request(`/api/leads/${encodeURIComponent(lead.id)}`, { method: "DELETE" }));
    showToast(`Removed ${label}`);
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}
