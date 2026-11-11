import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

const SLOT_COUNT = 3;

function titledProspect(lead) {
  if (!lead?.id) return lead;
  const stored = (state.leads || []).find((item) => item.id === lead.id);
  return stored ? { ...lead, ...stored } : lead;
}

function slotAssignments() {
  const slots = Array.from({ length: SLOT_COUNT }, () => null);
  for (const call of state.in_flight || []) {
    if (call.kind === "agent") continue;
    const index = Number.isInteger(call.slot_index) ? call.slot_index : null;
    if (index === null || index < 0 || index >= SLOT_COUNT) continue;
    const lead = titledProspect(call.lead || state.leads.find((item) => item.id === call.lead_id));
    const tone = call.lead_id === state.active_lead?.id
      ? "live"
      : call.state === "ringing"
        ? "ringing"
        : "dialing";
    slots[index] = { lead, tone, call };
  }
  if (state.active_lead) {
    const liveIndex = slots.findIndex((slot) => slot?.lead?.id === state.active_lead.id);
    if (liveIndex >= 0) slots[liveIndex].tone = "live";
  }
  const pool = state.pool || [];
  let poolCursor = 0;
  for (let index = 0; index < SLOT_COUNT; index += 1) {
    if (slots[index]) continue;
    while (poolCursor < pool.length) {
      const candidate = pool[poolCursor++];
      if (!slots.some((slot) => slot?.lead?.id === candidate.id)) {
        slots[index] = { lead: candidate, tone: "next", call: null };
        break;
      }
    }
  }
  return slots;
}

let lastSlotsKey = "";

export function renderAgentPowerSlots() {
  if (S.dashboardTab !== "aiDialerAgent" || !S.aiDialerSelectedAgentId) return;
  const host = byId("aiDialerAgent-activeCall");
  if (!host) return;
  const slots = slotAssignments();
  const starved = state.ai_dial_starved && state.running && !state.active_lead;
  const key = JSON.stringify([starved, slots.map((slot) => [slot?.lead?.id || null, slot?.tone || "empty"])]);
  if (key === lastSlotsKey) return;
  lastSlotsKey = key;
  host.replaceChildren();
  host.closest(".ai-dialer-menu")?.classList.toggle("ai-dial-starved", Boolean(starved));
  for (let index = 0; index < SLOT_COUNT; index += 1) {
    const slot = slots[index];
    const card = document.createElement("article");
    card.className = "power-line ai-power-slot";
    card.dataset.slot = String(index + 1);
    if (!slot) {
      card.dataset.tone = "empty";
      card.classList.toggle("is-starved", starved);
      const label = document.createElement("strong");
      label.textContent = `Line ${index + 1}`;
      const status = document.createElement("span");
      status.className = "power-line-state";
      status.textContent = starved ? "Waiting for pool" : "Empty";
      card.append(label, status);
    } else {
      card.dataset.tone = slot.tone;
      const name = document.createElement("strong");
      name.textContent = slot.lead?.name || slot.lead?.business || "Prospect";
      const status = document.createElement("span");
      status.className = "power-line-state";
      status.textContent = slot.tone === "live"
        ? "Live"
        : slot.tone === "ringing"
          ? "Ringing"
          : slot.tone === "dialing"
            ? "Dialing"
            : "Queued";
      card.append(name, status);
    }
    host.append(card);
  }
}
