import { postJson } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { STATUS_KEYS, STATUS_LABELS, byId } from "../../_core/format.js";
import { errorText, showToast } from "../../_core/notify.js";
import { render } from "../../core.js";
import { nextProspectLabel, queueProspect } from "./queue.js";

let saving = false;

export function bindCrmStatus() {
  byId("crmStatusButtons").addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (!button || saving) return;
    const lead = queueProspect();
    if (!lead || lead.status === button.dataset.status) return;
    saveCrmStatus(lead, button.dataset.status);
  });
}

export function renderCrmStatus() {
  const lead = queueProspect();
  const label = lead ? nextProspectLabel(lead) : "No prospect in the queue";
  byId("crmStatusTarget").textContent = label;
  const root = byId("crmStatusButtons");
  root.replaceChildren(...STATUS_KEYS.map((status) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "outcome-btn";
    button.dataset.status = status;
    button.textContent = STATUS_LABELS[status];
    button.disabled = !lead || saving;
    button.setAttribute("aria-pressed", lead?.status === status ? "true" : "false");
    return button;
  }));
}

async function saveCrmStatus(lead, status) {
  saving = true;
  renderCrmStatus();
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, {
      status,
      crm_only: true,
    });
    Object.assign(state, result.state);
    showToast(`${nextProspectLabel(lead)}: ${STATUS_LABELS[status]}`);
  } catch (error) {
    showToast(errorText(error, "Could not update the CRM status."), true);
  } finally {
    saving = false;
    render();
  }
}
