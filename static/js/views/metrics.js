import { statMemory, state } from "../store/state.js";
import { byId, formatMinutes, setText } from "../utils/format.js";
import { buildConnectionPieChart, buildMetricsLineChart, buildStatusPieChart } from "./charts.js";

export function rememberStat(id, text) {
  const node = byId(id);
  if (statMemory[id] !== undefined && statMemory[id] !== text) {
    const tile = node.closest(".stat-tile");
    tile.classList.remove("stat-flash");
    void tile.offsetWidth;
    tile.classList.add("stat-flash");
  }
  statMemory[id] = text;
  setText(id, text);
}

export function renderMetrics() {
  const today = state.metrics?.today || {};
  const allTime = state.metrics?.all_time || {};
  const daily = state.metrics?.daily || [];
  rememberStat("statDialsToday", String(today.dials || 0));
  setText("statDialsAll", String(allTime.dials || 0));
  rememberStat("statConnectedToday", String(today.connected || 0));
  setText("statConnectedAll", String(allTime.connected || 0));
  rememberStat("statBookedToday", String(today.booked || 0));
  setText("statBookedAll", String(allTime.booked || 0));
  rememberStat("statTalkToday", formatMinutes(today.talk_seconds));
  setText("statTalkAll", formatMinutes(allTime.talk_seconds));
  rememberStat("statSessionConversations", String(state.session_stats?.conversations || 0));
  buildMetricsLineChart(daily);
  buildStatusPieChart(state.leads);
  buildConnectionPieChart(allTime);
}
