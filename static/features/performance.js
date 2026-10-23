import { S, byId, postJson, registerRenderer, render, request, setText, showToast, state } from "../core.js";
import {
  CONVERSATION_MIN_SECONDS,
  DEFAULT_PERFORMANCE_RANGE,
  PERFORMANCE_RANGES,
  formatDuration,
  formatRate,
} from "../_core/format.js";
import { buildConnectionPieChart, buildStatusPieChart } from "./_performance/charts.js";
import { buildHeatmap, buildOutcomeBar, buildTrendChart } from "./_performance/trend.js";

const REFRESH_MS = 15000;
const RANGE_STORAGE_KEY = "prospect-desk-performance-range";
const RANGE_LABELS = { today: "Today", "7d": "Last 7 days", all: "All time" };
const COMPARED_WITH = { today: "the same hours yesterday", "7d": "the 7 days before" };
const EMPTY_TEXT = {
  today: "No calls yet today. Start a session and this page fills in as you dial.",
  "7d": "No calls in the last 7 days. Start a session and your numbers show up here.",
  all: "No calls yet. Start a session and your numbers show up here.",
};

function count(value) {
  return Number(value || 0).toLocaleString();
}

// Whole numbers above ten, one decimal below, a dash when there is nothing to divide by.
function ratio(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return value >= 10 ? String(Math.round(value)) : String(Number(value.toFixed(1)));
}

function setChange(id, change, lowerIsBetter = false) {
  const node = byId(id);
  const comparedWith = COMPARED_WITH[S.performanceRange];
  if (!comparedWith || typeof change !== "number" || !Number.isFinite(change)) {
    node.hidden = true;
    node.textContent = "";
    return;
  }
  const percent = Math.round(Math.abs(change) * 100);
  const direction = percent === 0 ? "flat" : change > 0 ? "up" : "down";
  const better = direction === "flat" ? null : (direction === "up") !== lowerIsBetter;
  const words = direction === "flat" ? "unchanged" : `${direction} ${percent}%`;
  node.hidden = false;
  node.dataset.tone = better === null ? "flat" : better ? "good" : "bad";
  node.textContent = `${direction === "up" ? "▲" : direction === "down" ? "▼" : "–"} ${percent}%`;
  node.setAttribute("aria-label", `${words} compared with ${comparedWith}`);
  node.title = `${words} compared with ${comparedWith}`;
}

function paintFunnel(metrics) {
  const value = (key) => metrics[key].value;
  for (const [name, key] of [["Dials", "dials"], ["Connected", "connected"], ["Conversations", "conversations"], ["Booked", "booked"]]) {
    setText(`funnel${name}Value`, count(value(key)));
    setChange(`funnel${name}Change`, metrics[key].change);
  }
  setText("rateConnectValue", formatRate(value("connect_rate")));
  setChange("rateConnectChange", metrics.connect_rate.change);
  setText("rateConversationValue", formatRate(value("conversation_rate")));
  setText("rateConversationLabel", `of connects talk ${CONVERSATION_MIN_SECONDS}s+`);
  setChange("rateConversationChange", metrics.conversation_rate.change);
  setText("rateBookingValue", formatRate(value("booking_rate")));
  setChange("rateBookingChange", metrics.booking_rate.change);
  setText("factTalkValue", formatDuration(value("avg_talk_seconds")));
  setChange("factTalkChange", metrics.avg_talk_seconds.change);
}

function paintHero(metrics) {
  const booked = metrics.booked.value;
  setText("heroValue", booked ? ratio(metrics.dials_per_meeting.value) : "—");
  setChange("heroChange", booked ? metrics.dials_per_meeting.change : null, true);
  const minutes = metrics.minutes_per_meeting.value;
  setText("heroMinutes", !booked
    ? "No meetings booked in this range."
    : minutes === null ? "Minutes of dialing per booked meeting: —" : `${ratio(minutes)} min of dialing per booked meeting`);
}

function paintGoal(goal) {
  const target = goal.target_minutes;
  const minutes = Math.floor(goal.minutes_today);
  setText("goalMinutesLabel", `${minutes} / ${target} min`);
  const track = byId("goalTrack");
  track.setAttribute("aria-valuemax", String(target));
  track.setAttribute("aria-valuenow", String(Math.min(minutes, target)));
  track.setAttribute("aria-valuetext", `${minutes} of ${target} minutes`);
  byId("goalProgress").style.width = `${Math.min(100, goal.minutes_today / target * 100)}%`;
  const remaining = Math.max(1, Math.ceil(target - goal.minutes_today));
  let message;
  if (goal.reached) message = "Today's block is done. Nice work showing up.";
  else if (goal.minutes_today > 0) message = `${remaining} min to go. Every call counts.`;
  else if (goal.current > 0 && !goal.active_today) message = `Dial today to keep your ${goal.current}-day streak going.`;
  else message = "Start a session to begin today's block.";
  if (goal.weekly_step > 0 && target > goal.base_minutes) message += ` Your target grows ${goal.weekly_step} min each week.`;
  setText("goalMessage", message);
  setText("goalStreak", goal.current > 0
    ? `${goal.current}-day streak${goal.best > goal.current ? ` · best ${goal.best}` : ""}`
    : "No streak yet. Your first dial day starts one.");
  if (byId("goalForm").hidden) {
    byId("goalMinutesInput").value = String(goal.base_minutes);
    byId("goalStepInput").value = String(goal.weekly_step);
  }
}

function paintBookings(bookings) {
  const note = byId("undatedNote");
  const undated = bookings.undated_count;
  note.hidden = undated === 0;
  note.textContent = undated
    ? `${undated} prospect${undated === 1 ? " is" : "s are"} marked booked without a date, so no range counts ${undated === 1 ? "it" : "them"}. Use Add booked meeting to date ${undated === 1 ? "it" : "them"}.`
    : "";
}

function paint(data) {
  const metrics = data.metrics;
  const hasData = metrics.dials.value > 0 || metrics.booked.value > 0;
  const empty = byId("performanceEmpty");
  empty.hidden = hasData;
  empty.textContent = EMPTY_TEXT[data.range];
  byId("performanceBody").hidden = !hasData;
  if (hasData) {
    paintHero(metrics);
    paintFunnel(metrics);
    buildTrendChart(data.trend);
  }
  setText("trendRange", RANGE_LABELS[data.range]);
  setText("outcomeRange", RANGE_LABELS[data.range]);
  setText("connectionRange", RANGE_LABELS[data.range]);
  paintGoal(data.goal);
  paintBookings(data.bookings);
  buildOutcomeBar(data.outcomes);
  buildHeatmap(data.heatmap);
  buildConnectionPieChart({ dials: metrics.dials.value, connected: metrics.connected.value });
}

function paintIfNew() {
  if (!state.performance || S.performancePainted === state.performance) return;
  S.performancePainted = state.performance;
  paint(state.performance);
}

export async function refreshPerformance() {
  if (S.performanceBusy) return;
  S.performanceBusy = true;
  const range = S.performanceRange;
  S.performanceFetchedAt = Date.now();
  try {
    const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "";
    const data = await request(`/api/performance?range=${encodeURIComponent(range)}&tz=${encodeURIComponent(timezone)}`);
    if (range === S.performanceRange) {
      state.performance = data;
      paintIfNew();
    } else {
      S.performanceFetchedAt = 0;
    }
  } catch (error) {
    showToast(error.message, true);
  } finally {
    S.performanceBusy = false;
  }
}

export function renderMetrics() {
  if (S.dashboardTab !== "performance") return;
  if (Date.now() - S.performanceFetchedAt > REFRESH_MS) refreshPerformance();
  paintIfNew();
  buildStatusPieChart(state.leads);
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
  refreshPerformance();
}

function leadLabel(lead) {
  const name = lead.name || lead.business || lead.phone || "Prospect";
  return lead.name && lead.business ? `${name} · ${lead.business}` : name;
}

function localDateValue(date) {
  const pad = (number) => String(number).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function openBookingDialog() {
  const undatedIds = new Set((state.performance?.bookings.undated || []).map((item) => item.id));
  const candidates = (state.leads || []).filter((lead) => !lead.booked_at && lead.status !== "disqualified");
  candidates.sort((a, b) => Number(undatedIds.has(b.id)) - Number(undatedIds.has(a.id)) || leadLabel(a).localeCompare(leadLabel(b)));
  const select = byId("bookingLeadSelect");
  select.replaceChildren(...candidates.map((lead) => {
    const option = document.createElement("option");
    option.value = lead.id;
    option.textContent = undatedIds.has(lead.id) ? `${leadLabel(lead)} (booked, no date)` : leadLabel(lead);
    return option;
  }));
  const today = localDateValue(new Date());
  byId("bookingDateInput").max = today;
  byId("bookingDateInput").value = today;
  byId("bookingError").hidden = true;
  byId("saveBooking").disabled = candidates.length === 0;
  if (!candidates.length) {
    byId("bookingError").hidden = false;
    byId("bookingError").textContent = "Every prospect already has a booking date.";
  }
  byId("bookingDialog").showModal();
}

async function saveBooking(event) {
  event.preventDefault();
  const error = byId("bookingError");
  const dateValue = byId("bookingDateInput").value;
  const [year, month, day] = dateValue.split("-").map(Number);
  const now = new Date();
  const noon = new Date(year, month - 1, day, 12, 0, 0);
  if (!dateValue || dateValue > localDateValue(now)) {
    error.hidden = false;
    error.textContent = "Pick a date that is today or earlier.";
    return;
  }
  byId("saveBooking").disabled = true;
  try {
    const result = await postJson("/api/bookings", {
      lead_id: byId("bookingLeadSelect").value,
      booked_at: (noon > now ? now : noon).toISOString(),
    });
    Object.assign(state, result.state);
    byId("bookingDialog").close();
    showToast("Booked meeting added");
    S.performanceFetchedAt = 0;
    render();
  } catch (failure) {
    error.hidden = false;
    error.textContent = failure.message;
  } finally {
    byId("saveBooking").disabled = false;
  }
}

function setGoalFormOpen(open) {
  byId("goalForm").hidden = !open;
  byId("goalEditButton").setAttribute("aria-expanded", String(open));
  if (open && state.performance) {
    byId("goalMinutesInput").value = String(state.performance.goal.base_minutes);
    byId("goalStepInput").value = String(state.performance.goal.weekly_step);
    byId("goalMinutesInput").focus();
  }
}

async function saveGoal(event) {
  event.preventDefault();
  byId("goalSaveButton").disabled = true;
  try {
    await postJson("/api/performance/goal", {
      daily_goal_minutes: Number(byId("goalMinutesInput").value),
      daily_goal_weekly_step: Number(byId("goalStepInput").value),
    });
    setGoalFormOpen(false);
    showToast("Daily goal saved");
    S.performanceFetchedAt = 0;
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    byId("goalSaveButton").disabled = false;
  }
}

export function bindPerformance() {
  const saved = localStorage.getItem(RANGE_STORAGE_KEY);
  S.performanceRange = PERFORMANCE_RANGES.includes(saved) ? saved : DEFAULT_PERFORMANCE_RANGE;
  for (const button of document.querySelectorAll("[data-performance-range]")) {
    const selected = button.dataset.performanceRange === S.performanceRange;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
    button.addEventListener("click", () => setRange(button.dataset.performanceRange));
  }
  byId("performanceTabButton").addEventListener("click", () => {
    S.performanceFetchedAt = 0;
    render();
  });
  byId("goalEditButton").addEventListener("click", () => setGoalFormOpen(byId("goalForm").hidden));
  byId("goalCancelButton").addEventListener("click", () => setGoalFormOpen(false));
  byId("goalForm").addEventListener("submit", saveGoal);
  byId("addBookingButton").addEventListener("click", openBookingDialog);
  byId("bookingForm").addEventListener("submit", saveBooking);
  for (const id of ["closeBooking", "cancelBooking"]) byId(id).addEventListener("click", () => byId("bookingDialog").close());
}

registerRenderer(renderMetrics);
