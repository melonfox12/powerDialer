import { state } from "../../_core/state.js";
import { byId, initials } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";

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
  const nextLabel = firstUp ? nextProspectLabel(firstUp) : "";
  primary.textContent = queueLead
    ? (queueLead.name || queueLead.business || "")
    : poolCount > 0 || firstUp
      ? (nextLabel ? `${poolCount} ready · Next: ${nextLabel}` : `${poolCount} ready`)
      : "No prospects in queue";
  const place = prospectPlace(queueLead || firstUp);
  if (place) {
    const where = document.createElement("span");
    where.className = "queue-place";
    where.textContent = place;
    primary.append(document.createTextNode(" "), where);
  }
  const secondary = document.createElement("span");
  secondary.textContent = "";
  copy.append(primary, secondary);
  activeCall.append(avatar, copy);
}

export function queueProspect() {
  if (state.active_lead) return state.active_lead;
  if (state.pending_outcome?.id) return state.pending_outcome;
  const live = (state.in_flight || []).find((call) => call.kind !== "agent" && (call.lead || call.lead_id));
  if (live?.lead) return live.lead;
  if (live?.lead_id) return { id: live.lead_id };
  return state.next_lead || null;
}

function prospectPlace(lead) {
  const source = lead?.city || lead?.state || lead?.fields
    ? lead
    : state.leads?.find((item) => item.id && item.id === lead?.id) || lead;
  const city = locationOf(source, "city");
  const region = locationOf(source, "state");
  if (city && region) return `${city}, ${region}`;
  return city || region;
}

function locationOf(lead, key) {
  const direct = String(lead?.[key] || "").trim();
  if (direct) return direct;
  for (const [name, value] of Object.entries(lead?.fields || {})) {
    if (name.trim().toLowerCase() === key) return String(value || "").trim();
  }
  return "";
}

export function nextProspectLabel(lead) {
  const business = String(lead.business || "").trim();
  const firstName = String(lead.name || "").trim().split(/\s+/)[0] || "";
  if (firstName && business) return `${firstName} - ${business}`;
  return business || lead.name || formatPhoneNumber(lead.phone) || "";
}
