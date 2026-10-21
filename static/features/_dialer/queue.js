import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";

export function renderQueueStrip() {
  const activeCall = byId("activeCall");
  const lines = dialLines();
  activeCall.replaceChildren();
  if (!lines.length) {
    const empty = document.createElement("p");
    empty.className = "power-line-empty";
    empty.textContent = "No prospects in queue";
    activeCall.append(empty);
    return;
  }
  for (const line of lines) activeCall.append(prospectCard(line));
}

function dialLines() {
  const shown = [];
  const seen = new Set();
  const add = (lead, tone) => {
    const source = titledProspect(lead);
    if (!source?.id || seen.has(source.id) || shown.length >= 3) return;
    seen.add(source.id);
    shown.push({ lead: source, tone });
  };
  if (state.active_lead) add(state.active_lead, "live");
  for (const call of state.in_flight || []) {
    const tone = call.lead_id === state.active_lead?.id ? "live" : call.state === "ringing" ? "ringing" : "dialing";
    add(call.lead || { id: call.lead_id }, tone);
  }
  for (const lead of state.pool || []) add(lead, "next");
  if (!shown.length && state.next_lead) add(state.next_lead, "next");
  if (!shown.length && state.pending_outcome) add(state.pending_outcome, "next");
  return shown;
}

function prospectCard(line) {
  const card = document.createElement("article");
  card.className = "power-line";
  card.dataset.tone = line.tone;
  const name = document.createElement("strong");
  name.textContent = line.lead.name || line.lead.business || "Prospect";
  card.append(name);
  const place = prospectPlace(line.lead);
  if (place) {
    const where = document.createElement("span");
    where.className = "queue-place";
    where.textContent = place;
    card.append(where);
  }
  const reviews = reviewCount(line.lead);
  if (reviews) {
    const count = document.createElement("span");
    count.className = "queue-reviews";
    count.textContent = reviews;
    card.append(count);
  }
  const status = document.createElement("span");
  status.className = "power-line-state";
  status.textContent = line.tone === "live" ? "Live" : line.tone === "ringing" ? "Ringing" : line.tone === "dialing" ? "Dialing" : "Next";
  card.append(status);
  return card;
}

export function queueProspect() {
  if (state.active_lead) return state.active_lead;
  if (state.pending_outcome?.id) return state.pending_outcome;
  const live = (state.in_flight || []).find((call) => call.kind !== "agent" && (call.lead || call.lead_id));
  if (live?.lead) return live.lead;
  if (live?.lead_id) return { id: live.lead_id };
  return state.next_lead || null;
}

function appendProspectFacts(primary, lead) {
  const source = titledProspect(lead);
  const place = prospectPlace(source);
  if (place) {
    const where = document.createElement("span");
    where.className = "queue-place";
    where.textContent = place;
    primary.append(document.createTextNode(" "), where);
  }
  const reviews = reviewCount(source);
  if (reviews) {
    const count = document.createElement("span");
    count.className = "queue-reviews";
    count.textContent = reviews;
    primary.append(document.createTextNode(" "), count);
  }
}

function titledProspect(lead) {
  if (!lead?.id) return lead || null;
  const stored = (state.leads || []).find((item) => item.id === lead.id);
  return stored ? { ...lead, ...stored } : lead;
}

function prospectPlace(lead) {
  const city = locationOf(lead, "city");
  const region = locationOf(lead, "state");
  if (city && region) return `${city}, ${region}`;
  return city || region;
}

function reviewCount(lead) {
  const count = lead?.review_count;
  if (count === 0 || count) {
    const total = Number(count);
    if (!Number.isFinite(total)) return String(count);
    return `${total} review${total === 1 ? "" : "s"}`;
  }
  return "";
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
