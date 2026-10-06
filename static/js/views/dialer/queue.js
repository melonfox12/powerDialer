import { state } from "../../../_core/state.js";
import { byId, initials } from "../../../_core/format.js";
import { formatPhoneNumber } from "../../../_core/phone.js";

export function renderQueueStrip(active, pending, target) {
  const activeCall = byId("activeCall");
  activeCall.replaceChildren();
  const avatar = document.createElement("div");
  avatar.className = "active-avatar";
  avatar.textContent = target ? initials(target.name || target.business) : "PD";
  const copy = document.createElement("div");
  copy.className = "active-copy";
  const primary = document.createElement("strong");
  const queueLead = active || pending || (state.in_flight || []).find((call) => call.state === "ringing")?.lead;
  const poolCount = state.pool?.length || 0;
  const firstUp = state.next_lead;
  const nextLabel = firstUp ? (firstUp.business || firstUp.name || formatPhoneNumber(firstUp.phone)) : "";
  primary.textContent = queueLead
    ? (queueLead.name || queueLead.business || "")
    : poolCount > 0 || firstUp
      ? (nextLabel ? `${poolCount} ready · Next: ${nextLabel}` : `${poolCount} ready`)
      : "No prospects in queue";
  const secondary = document.createElement("span");
  secondary.textContent = "";
  copy.append(primary, secondary);
  activeCall.append(avatar, copy);
}
