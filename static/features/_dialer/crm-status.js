import { postJson } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { byId, leavesQueueForGood } from "../../_core/format.js";
import { errorText, showToast } from "../../_core/notify.js";
import { render } from "../../core.js";
import { nextProspectLabel, queueProspect } from "./queue.js";

const DIALER_STATUSES = [
  { status: "call", label: "Callback", className: "outcome-btn outcome-btn-call" },
  { status: "booked", label: "Booked", className: "outcome-btn outcome-btn-booked" },
  { status: "disqualified", label: "Disqualified", className: "outcome-btn outcome-btn-disqualified" },
];

let saving = false;

export function bindCrmStatus() {
  byId("crmStatusButtons").addEventListener("click", (event) => {
    const button = event.target.closest("[data-status]");
    if (!button || saving) return;
    const lead = queueProspect();
    if (!lead) return;
    if (button.dataset.status === "booked" && lead.status === "booked") return;
    saveCrmStatus(lead, button.dataset.status, button.textContent);
  });
}

export function renderCrmStatus() {
  const lead = queueProspect();
  const label = lead ? nextProspectLabel(lead) : "No prospect in the queue";
  byId("crmStatusTarget").textContent = label;
  const root = byId("crmStatusButtons");
  root.replaceChildren(...DIALER_STATUSES.map((item) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = item.className;
    button.dataset.status = item.status;
    button.textContent = item.label;
    button.disabled = !lead || saving || leavesQueueForGood(lead, item.status);
    button.setAttribute("aria-pressed", lead?.status === item.status ? "true" : "false");
    return button;
  }));
}

async function saveCrmStatus(lead, status, label) {
  saving = true;
  renderCrmStatus();
  const name = nextProspectLabel(lead);
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, {
      status,
      crm_only: true,
    });
    Object.assign(state, result.state);
    if (status === "call") showToast(`Callback started for ${name}`);
    else if (status === "disqualified") showToast(`${name} will never be dialed again`);
    else showToast(`${name}: ${label}`);
  } catch (error) {
    showToast(errorText(error, "Could not update the CRM status."), true);
  } finally {
    saving = false;
    render();
  }
}
