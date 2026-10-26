import { S, byId, postJson, registerRenderer, request, setText, showToast, state } from "../core.js";
import {
  DEFAULT_PERFORMANCE_RANGE,
  PERFORMANCE_RANGES,
  formatRate,
} from "../_core/format.js";
import { bindPerformanceChart, buildPerformanceLineChart } from "./_performance/line-chart.js";

const REFRESH_MS = 30000;
const RANGE_STORAGE_KEY = "prospect-desk-performance-range";
const LEGACY_RANGE_MAP = { today: "day", "7d": "week", all: "month" };
const GOAL_PERIOD_LABELS = {
  day: { conversations: "Conversations today", talk: "Talk time today" },
  week: { conversations: "Conversations this week", talk: "Talk time this week" },
  month: { conversations: "Conversations this month", talk: "Talk time this month" },
};

function performanceAuthReady() {
  if (!S.googleAuthEnabled) return true;
  return Boolean(S.accessToken);
}

function normalizePerformancePayload(data) {
  if (!data || typeof data !== "object") return null;
  if (data.daily && data.funnel && data.trend) return data;
  if (!data.metrics) return null;
  const metrics = data.metrics;
  const goal = data.goal || {};
  const value = (key) => Number(metrics[key]?.value ?? 0);
  return {
    range: data.range,
    conversation_min_seconds: data.conversation_min_seconds,
    has_activity: Boolean(data.has_dials),
    counts: {
      dials: value("dials"),
      connected: value("connected"),
      conversations: value("conversations"),
      booked: value("booked"),
      talk_seconds: 0,
    },
    funnel: {
      dials_to_connected: metrics.connect_rate?.value ?? null,
      connected_to_conversations: metrics.conversation_rate?.value ?? null,
      conversations_to_booked: metrics.booking_rate?.value ?? null,
      connected_to_booked: metrics.pickup_booking_rate?.value ?? metrics.booking_rate?.value ?? null,
    },
    trend: data.trend || { grain: "day", buckets: [] },
    daily: {
      range: data.range,
      conversations: value("conversations"),
      conversation_goal: 30,
      talk_minutes: Number(goal.minutes_today ?? 0),
      talk_minutes_goal: Number(goal.target_minutes ?? 60),
    },
  };
}

function talkLabel(minutes) {
  const totalSeconds = Math.round(Number(minutes) * 60);
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  if (hours) return mins ? `${hours}h ${mins}m` : `${hours}h`;
  if (mins) return `${mins}m`;
  return `${totalSeconds % 60}s`;
}

function paintDailyGoals(daily, rangeKey) {
  if (!daily || typeof daily !== "object") return;
  const range = GOAL_PERIOD_LABELS[rangeKey || daily.range] ? (rangeKey || daily.range) : S.performanceRange;
  const labels = GOAL_PERIOD_LABELS[range] || GOAL_PERIOD_LABELS.week;
  setText("dailyConversationLabel", labels.conversations);
  setText("dailyTalkLabel", labels.talk);
  const conversations = Number(daily.conversations ?? 0);
  const conversationGoal = daily.conversation_goal;
  const talkMinutes = daily.talk_minutes;
  const talkGoal = daily.talk_minutes_goal;
  setText("dailyConversationsValue", String(conversations));
  byId("dailyConversationGoalButton").textContent = String(conversationGoal);
  setText("dailyTalkValue", talkLabel(talkMinutes));
  byId("dailyTalkGoalButton").textContent = `${talkGoal}m`;
  const conversationTrack = byId("dailyConversationTrack");
  conversationTrack.setAttribute("aria-valuemax", String(conversationGoal));
  conversationTrack.setAttribute("aria-valuenow", String(Math.min(conversations, conversationGoal)));
  conversationTrack.setAttribute("aria-valuetext", `${conversations} of ${conversationGoal} conversations`);
  byId("dailyConversationFill").style.width = `${Math.min(100, conversationGoal ? conversations / conversationGoal * 100 : 0)}%`;
  const talkTrack = byId("dailyTalkTrack");
  talkTrack.setAttribute("aria-valuemax", String(talkGoal));
  talkTrack.setAttribute("aria-valuenow", String(Math.min(Math.floor(talkMinutes), talkGoal)));
  talkTrack.setAttribute("aria-valuetext", `${talkLabel(talkMinutes)} of ${talkGoal} minutes`);
  byId("dailyTalkFill").style.width = `${Math.min(100, talkGoal ? talkMinutes / talkGoal * 100 : 0)}%`;
}

function paintFunnel(funnel, counts) {
  if (!funnel) return;
  const c = counts || {};
  setText("funnelCountDials", String(c.dials ?? 0));
  const transcriptDials = Number(c.conversations ?? 0);
  const pickupRate = c.dials ? transcriptDials / c.dials : null;
  const bookedDials = Number(c.booked ?? 0);
  const bookedRate = c.dials ? bookedDials / c.dials : null;
  const rateCards = [
    ["funnelRatePickups", "funnelDetailPickups", "funnelRatePickupsBar", pickupRate, transcriptDials, c.dials],
    ["funnelRateBooked", "funnelDetailBooked", "funnelRateBookedBar", bookedRate, bookedDials, c.dials],
  ];
  for (const [valueId, detailId, barId, ratio, num, den] of rateCards) {
    setText(valueId, formatRate(ratio));
    const detail = byId(detailId);
    if (detail) detail.textContent = `${num ?? 0} of ${den ?? 0}`;
    const bar = byId(barId);
    bar.style.width = typeof ratio === "number" && Number.isFinite(ratio) ? `${Math.min(100, ratio * 100)}%` : "0%";
  }
}

function normalizeTrend(trend) {
  const base = trend && typeof trend === "object" ? trend : { grain: "day", buckets: [] };
  const buckets = Array.isArray(base.buckets) ? base.buckets : [];
  return {
    ...base,
    buckets: buckets.map((bucket) => {
      const pickupsRaw = bucket?.pickups ?? bucket?.conversations;
      const pickups = Number(pickupsRaw);
      return {
        ...bucket,
        pickups: Number.isFinite(pickups) ? Math.max(0, pickups) : 0,
      };
    }),
  };
}

function paint(data) {
  if (!data) return;
  if (data.range && data.range !== S.performanceRange) return;
  paintDailyGoals(data.daily, data.range);
  paintFunnel(data.funnel, data.counts);
  schedulePerformanceLineChart(normalizeTrend(data.trend));
}

function schedulePerformanceLineChart(trend) {
  buildPerformanceLineChart(trend);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      if (S.dashboardTab === "performance") buildPerformanceLineChart(trend);
    });
  });
}

function paintIfNew() {
  if (!state.performance || S.performancePainted === state.performance) return;
  S.performancePainted = state.performance;
  paint(state.performance);
}

export async function refreshPerformance() {
  if (S.performanceBusy) return;
  if (!performanceAuthReady()) return;
  S.performanceBusy = true;
  const range = S.performanceRange;
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    const raw = await request(`/api/performance?range=${encodeURIComponent(range)}&tz=${encodeURIComponent(timezone)}`);
    const data = normalizePerformancePayload(raw);
    if (!data) {
      throw new Error("Performance data is unavailable. Restart the app server and reload the page.");
    }
    if (range === S.performanceRange) {
      state.performance = data;
      S.performanceFetchedAt = Date.now();
      S.performancePainted = null;
      paintIfNew();
    }
  } catch (error) {
    S.performanceFetchedAt = 0;
    if (performanceAuthReady()) showToast(error.message, true);
  } finally {
    S.performanceBusy = false;
  }
}

export function renderMetrics() {
  if (S.dashboardTab !== "performance") return;
  if (Date.now() - S.performanceFetchedAt > REFRESH_MS) refreshPerformance();
  paintIfNew();
}

export function repaintPerformanceChart() {
  const trend = state.performance?.trend;
  if (!trend) return;
  schedulePerformanceLineChart(normalizeTrend(trend));
}

function setRange(range) {
  S.performanceRange = PERFORMANCE_RANGES.includes(range) ? range : DEFAULT_PERFORMANCE_RANGE;
  localStorage.setItem(RANGE_STORAGE_KEY, S.performanceRange);
  for (const button of document.querySelectorAll("[data-performance-range]")) {
    const selected = button.dataset.performanceRange === S.performanceRange;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
  S.performanceFetchedAt = 0;
  S.performancePainted = null;
  refreshPerformance();
}

async function editGoal(field) {
  const daily = state.performance?.daily;
  if (!daily) return;
  const current = field === "conversations" ? daily.conversation_goal : daily.talk_minutes_goal;
  const label = field === "conversations" ? "Daily conversation goal" : "Daily talk-time goal (minutes)";
  const raw = window.prompt(label, String(current));
  if (raw === null) return;
  const value = Number(raw);
  if (!Number.isFinite(value) || value < 1) {
    showToast("Enter a whole number at least 1.", true);
    return;
  }
  const payload = field === "conversations"
    ? { daily_conversation_goal: value }
    : { daily_goal_minutes: value };
  try {
    await postJson("/api/performance/goal", payload);
    showToast("Daily goal saved");
    S.performanceFetchedAt = 0;
    await refreshPerformance();
  } catch (error) {
    showToast(error.message, true);
  }
}

function normalizeSavedRange(saved) {
  if (PERFORMANCE_RANGES.includes(saved)) return saved;
  if (saved && LEGACY_RANGE_MAP[saved]) return LEGACY_RANGE_MAP[saved];
  return DEFAULT_PERFORMANCE_RANGE;
}

export function bindPerformance() {
  const saved = normalizeSavedRange(localStorage.getItem(RANGE_STORAGE_KEY));
  S.performanceRange = saved;
  localStorage.setItem(RANGE_STORAGE_KEY, S.performanceRange);
  for (const button of document.querySelectorAll("[data-performance-range]")) {
    const selected = button.dataset.performanceRange === S.performanceRange;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.addEventListener("click", () => setRange(button.dataset.performanceRange));
  }
  bindPerformanceChart();
  byId("performanceTabButton").addEventListener("click", () => {
    S.performanceFetchedAt = 0;
    renderMetrics();
  });
  byId("dailyConversationGoalButton").addEventListener("click", () => editGoal("conversations"));
  byId("dailyTalkGoalButton").addEventListener("click", () => editGoal("talk"));
}

registerRenderer(renderMetrics);
