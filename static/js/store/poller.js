import { request } from "../api/client.js";
import { arcadeSensory } from "../features/arcade/controller/index.js";
import { byId } from "../utils/format.js";
import { showToast } from "../views/dialogs.js";
import { render } from "../views/render.js";
import { S, seenSensoryActivity, state } from "./state.js";

export function processSensoryActivity(activity) {
  const keyFor = (entry) => `${entry.timestamp || ""}:${entry.source || ""}:${entry.message || ""}`;
  if (!S.sensoryActivityPrimed) {
    activity.forEach((entry) => seenSensoryActivity.add(keyFor(entry)));
    S.sensoryActivityPrimed = true;
    return;
  }
  for (const entry of activity) {
    const key = keyFor(entry);
    if (seenSensoryActivity.has(key)) continue;
    seenSensoryActivity.add(key);
    const failedCall = /call request failed|call failed|busy signal/i.test(entry.message || "");
    if (failedCall && ["call", "error"].includes(entry.source)) arcadeSensory.reset();
  }
  if (seenSensoryActivity.size > 160) {
    const recent = activity.map(keyFor);
    seenSensoryActivity.clear();
    recent.forEach((key) => seenSensoryActivity.add(key));
  }
}

export async function refreshState() {
  if (S.pollBusy) return;
  S.pollBusy = true;
  try {
    const live = await request("/api/live");
    const needTable = live.leads_version !== state.leads_version || !Array.isArray(state.leads);
    if (needTable) {
      Object.assign(state, await request("/api/state"));
    } else {
      const leads = state.leads;
      const pool = state.pool;
      Object.assign(state, live);
      state.leads = leads;
      state.pool = pool;
      if (live.active_lead) {
        const index = leads.findIndex((lead) => lead.id === live.active_lead.id);
        if (index >= 0) leads[index] = live.active_lead;
      }
      if (live.pending_outcome) {
        const index = leads.findIndex((lead) => lead.id === live.pending_outcome.id);
        if (index >= 0) leads[index] = live.pending_outcome;
      }
    }
    if (Date.now() - S.metricsFetchedAt > 15000) {
      S.metricsFetchedAt = Date.now();
      const metricsResult = await request("/api/metrics").catch(() => null);
      if (metricsResult) state.metrics = metricsResult;
    }
    processSensoryActivity(state.activity_log || []);
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    S.pollBusy = false;
  }
}

export function startPolling() {
  setInterval(() => { if (!byId("loginGate").hidden) return; refreshState(); }, 1500);
}
