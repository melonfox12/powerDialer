import { request } from "./api.js";
import { S, state } from "./state.js";
import { byId } from "./format.js";
import { showToast } from "./notify.js";
import {
  leadsCatalogIsStale,
  mergeLiveLeadPatches,
  mergeLiveState,
  refreshLeadsCatalogForTab,
} from "./sync-state.js";
import { render } from "../core.js";

export async function refreshState() {
  if (S.pollBusy) return;
  S.pollBusy = true;
  try {
    const live = await request("/api/live");
    const prevVersion = state.leads_version;
    mergeLiveState(live);
    if (leadsCatalogIsStale(live.leads_version) || live.leads_version !== prevVersion) {
      await refreshLeadsCatalogForTab();
    } else {
      mergeLiveLeadPatches(live);
    }
    if (Date.now() - S.metricsFetchedAt > 15000) {
      S.metricsFetchedAt = Date.now();
      const metricsResult = await request("/api/metrics").catch(() => null);
      if (metricsResult) state.metrics = metricsResult;
    }
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    S.pollBusy = false;
  }
}

let pollingStarted = false;

export function startPolling() {
  if (pollingStarted) return;
  pollingStarted = true;
  setInterval(() => {
    if (!byId("loginGate").hidden) return;
    refreshState();
  }, 1500);
}