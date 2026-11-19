import { registerRenderer } from "../../_core/registry.js";
import { request } from "../../_core/api.js";
import { setText } from "../../_core/format.js";
import { activeCampaignId } from "./campaign-chrome.js";

const SCOPE_KEY = "godial-workflow-funnel-scope";

/** @type {"campaign" | "today"} */
let funnelScope = "campaign";
/** @type {object | null} */
let lastStats = null;
let bound = false;

function workflowCanvasInteracting() {
  const view = document.getElementById("workflowViewport");
  return Boolean(view?.classList.contains("is-workflow-interacting") || view?.classList.contains("is-panning"));
}

function loadScope() {
  try {
    funnelScope = localStorage.getItem(SCOPE_KEY) === "today" ? "today" : "campaign";
  } catch {
    funnelScope = "campaign";
  }
}

function saveScope() {
  try {
    localStorage.setItem(SCOPE_KEY, funnelScope);
  } catch {
    // ignore
  }
}

function formatRate(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Math.round(Number(value) * 100)}%`;
}

function formatMoney(value) {
  const num = Number(value);
  if (!Number.isFinite(num)) return "$0.00";
  return `$${num.toFixed(2)}`;
}

function formatMinutes(value) {
  const num = Number(value);
  if (!Number.isFinite(num) || num <= 0) return "0 call min";
  const rounded = Math.round(num * 10) / 10;
  return `${rounded} call min`;
}

function paintFunnelToggle() {
  for (const btn of document.querySelectorAll(".workflow-funnel-toggle[data-funnel-scope]")) {
    const scope = btn.getAttribute("data-funnel-scope");
    const active = scope === funnelScope;
    btn.classList.toggle("is-active", active);
    btn.setAttribute("aria-pressed", active ? "true" : "false");
    btn.disabled = false;
  }
}

function paintStats(payload) {
  const funnel = payload?.funnel || {};
  setText("workflowFunnelDials", String(funnel.dials ?? 0));
  setText("workflowFunnelPickups", String(funnel.pickups ?? 0));
  setText("workflowFunnelConversations", String(funnel.conversations ?? 0));
  setText("workflowFunnelQualified", String(funnel.qualified ?? 0));
  setText("workflowFunnelBooked", String(funnel.booked ?? 0));
  const rates = funnel.rates || {};
  setText("workflowFunnelRatePickups", formatRate(rates.pickups));
  setText("workflowFunnelRateConversations", formatRate(rates.conversations));
  setText("workflowFunnelRateQualified", formatRate(rates.qualified));
  setText("workflowFunnelRateBooked", formatRate(rates.booked));

  const live = payload?.live || {};
  setText("workflowLiveMinutes", formatMinutes(live.call_minutes));
  setText("workflowLiveCost", formatMoney(live.cost_usd));

  const hours = payload?.calling_hours || {};
  const inside = hours.inside_window ? " · in window" : " · outside window";
  setText("workflowCallingHoursValue", `${hours.label || "—"}${hours.label ? inside : ""}`);
  const hoursEl = document.getElementById("workflowCallingHours");
  if (hoursEl) {
    hoursEl.classList.toggle("is-in-window", Boolean(hours.inside_window));
    hoursEl.classList.toggle("is-outside-window", hours.label && !hours.inside_window);
  }

  const liveWrap = document.querySelector(".workflow-viewport-live");
  if (liveWrap) {
    liveWrap.classList.toggle("is-campaign-live", Boolean(live.is_live));
  }
}

export async function refreshCampaignStats() {
  if (document.getElementById("workflowTabPanel")?.hidden) return lastStats;
  if (workflowCanvasInteracting()) return lastStats;
  const campaignId = activeCampaignId();
  if (!campaignId) {
    lastStats = null;
    return lastStats;
  }
  try {
    lastStats = await request(
      `/api/campaigns/${encodeURIComponent(campaignId)}/stats?scope=${encodeURIComponent(funnelScope)}`,
    );
    paintStats(lastStats);
    paintFunnelToggle();
    return lastStats;
  } catch {
    lastStats = null;
    return lastStats;
  }
}

export function bindCampaignStats() {
  if (bound) return;
  bound = true;
  loadScope();
  paintFunnelToggle();
  for (const btn of document.querySelectorAll(".workflow-funnel-toggle[data-funnel-scope]")) {
    btn.addEventListener("click", () => {
      const scope = btn.getAttribute("data-funnel-scope");
      if (scope !== "campaign" && scope !== "today") return;
      funnelScope = scope;
      saveScope();
      void refreshCampaignStats();
    });
  }
  registerRenderer(refreshCampaignStats, "end", "workflow");
  window.addEventListener("godial-workflow-flow", () => {
    void refreshCampaignStats();
  });
}