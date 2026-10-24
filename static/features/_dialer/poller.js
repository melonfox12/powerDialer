import { request } from "../../_core/api.js";
import { arcadeSensory } from "../arcade.js";
import { S, seenSensoryActivity, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import {
  applyLeadsCatalog,
  fetchLeadsCatalog,
  mergeLeadPatch,
  mergeLiveState,
} from "../../_core/sync-state.js";
import { render } from "../../core.js";

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
    const prevVersion = state.leads_version;
    mergeLiveState(live);
    if (!Array.isArray(state.leads) || live.leads_version !== prevVersion) {
      applyLeadsCatalog(await fetchLeadsCatalog());
    } else if (Array.isArray(state.leads)) {
      mergeLeadPatch(state.leads, live.active_lead);
      mergeLeadPatch(state.leads, live.pending_outcome);
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
