import { byId, dayLabel, formatRate } from "../../_core/format.js";

/** Same three metrics as the period total cards (counts per bucket from performance.py). */
export const PERFORMANCE_CHART_SERIES = [
  { key: "dials", label: "Dials", className: "line-series-dials", pointClass: "line-point-dials", marker: true },
  { key: "conversations", label: "Conversations", className: "line-series-connected", pointClass: "line-point-connected", marker: true },
  { key: "booked", label: "Booked", className: "line-series-booked", pointClass: "line-point-booked", marker: true },
];

const SERIES = PERFORMANCE_CHART_SERIES;

let visible = { dials: true, conversations: true, booked: true };
let lastTrend = null;

function hourLabel(hour) {
  return `${hour % 12 || 12}${hour < 12 ? "a" : "p"}`;
}

function bucketTitle(bucket, grain) {
  if (grain === "hour") {
    const when = new Date(bucket.at);
    return when.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  }
  const date = new Date(`${bucket.date}T12:00:00`);
  return date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric" });
}

function bucketCenterMs(bucket, grain) {
  if (grain === "hour") return Date.parse(bucket.at) + 30 * 60 * 1000;
  return Date.parse(`${bucket.date}T12:00:00`);
}

function periodBounds(trend, buckets, grain) {
  const start = Date.parse(trend?.period_start || "");
  const end = Date.parse(trend?.period_end || "");
  if (Number.isFinite(start) && Number.isFinite(end) && end > start) {
    return { start, end };
  }
  if (!buckets.length) return { start: 0, end: 1 };
  const first = bucketCenterMs(buckets[0], grain) - (grain === "hour" ? 30 * 60 * 1000 : 12 * 60 * 60 * 1000);
  const last = bucketCenterMs(buckets[buckets.length - 1], grain) + (grain === "hour" ? 30 * 60 * 1000 : 12 * 60 * 60 * 1000);
  return { start: first, end: last };
}

function bucketAxisLabel(bucket, grain, count, index) {
  if (grain === "hour") {
    if (index === 0 || index === count - 1) {
      const when = new Date(bucket.at);
      return when.toLocaleString(undefined, { month: "numeric", day: "numeric", hour: "numeric" });
    }
    return hourLabel(bucket.hour);
  }
  if (count > 14) return `${Number(bucket.date.slice(5, 7))}/${Number(bucket.date.slice(8, 10))}`;
  return dayLabel(bucket.date);
}

function paintLegend(onToggle) {
  const legend = byId("performanceChartLegend");
  if (!legend) return;
  legend.replaceChildren(...SERIES.map((series) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "performance-legend-toggle";
    button.dataset.series = series.key;
    button.setAttribute("aria-pressed", String(visible[series.key]));
    button.innerHTML = `<i class="legend-line ${series.className.replace("line-series-", "legend-line-")}" aria-hidden="true"></i>${series.label}`;
    button.addEventListener("click", () => {
      visible[series.key] = !visible[series.key];
      button.setAttribute("aria-pressed", String(visible[series.key]));
      onToggle();
    });
    return button;
  }));
}

const CHART_HEIGHT = 320;
const CHART_WIDTH = 960;

function chartSize(container) {
  const hidden = container.closest("[hidden]") || container.hidden;
  if (hidden) return { width: CHART_WIDTH, height: CHART_HEIGHT };
  const rect = container.getBoundingClientRect();
  const width = Math.round(rect.width) || container.clientWidth || CHART_WIDTH;
  const height = Math.round(rect.height) || container.clientHeight || CHART_HEIGHT;
  return {
    width: Math.max(width, 320),
    height: Math.max(height, 280),
  };
}

export function buildPerformanceLineChart(trend) {
  const container = byId("performanceLineChart");
  const empty = byId("performanceChartEmpty");
  if (!container || !empty) return;
  const buckets = trend?.buckets || [];
  const grain = trend?.grain || "day";
  lastTrend = trend;
  const hasData = buckets.length > 0;
  empty.hidden = hasData;
  container.hidden = !hasData;
  if (!hasData) {
    container.textContent = "";
    container.setAttribute("aria-label", "No activity in this range");
    return;
  }
  const { width, height } = chartSize(container);
  const left = 36;
  const right = 12;
  const top = 14;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const { start: periodStart, end: periodEnd } = periodBounds(trend, buckets, grain);
  const span = Math.max(periodEnd - periodStart, 1);
  const maxValue = Math.max(1, ...buckets.flatMap((bucket) => [bucket.dials, bucket.conversations, bucket.booked]));
  const xForTime = (ms) => {
    const clamped = Math.min(periodEnd, Math.max(periodStart, ms));
    return left + ((clamped - periodStart) / span) * plotWidth;
  };
  const xForIndex = (index) => xForTime(bucketCenterMs(buckets[index], grain));
  const yFor = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const parts = [];

  parts.push(`<line x1="${left}" y1="${top}" x2="${left}" y2="${top + plotHeight}" class="line-chart-axis-edge" />`);
  parts.push(`<line x1="${width - right}" y1="${top}" x2="${width - right}" y2="${top + plotHeight}" class="line-chart-axis-edge" />`);
  parts.push(`<line x1="${left}" y1="${top + plotHeight}" x2="${width - right}" y2="${top + plotHeight}" class="line-chart-axis-edge" />`);

  for (const fraction of [0, 0.5, 1]) {
    const y = top + plotHeight * (1 - fraction);
    const gridClass = fraction === 0 ? "line-chart-axis-baseline" : "line-chart-grid";
    parts.push(`<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="${gridClass}" />`);
    parts.push(`<text x="${left - 8}" y="${y + 4}" class="line-chart-y-label">${Math.round(maxValue * fraction)}</text>`);
  }

  for (const series of SERIES) {
    if (!visible[series.key]) continue;
    const points = buckets.map((bucket, index) => `${xForIndex(index)},${yFor(bucket[series.key] || 0)}`);
    parts.push(`<polyline points="${points.join(" ")}" class="line-series ${series.className}" />`);
    if (series.marker) {
      buckets.forEach((bucket, index) => {
        const value = bucket[series.key] || 0;
        parts.push(`<circle cx="${xForIndex(index)}" cy="${yFor(value)}" r="3" class="line-point ${series.pointClass}"><title>${bucketTitle(bucket, grain)}: ${series.label} ${value}</title></circle>`);
      });
    }
  }

  const step = Math.ceil(buckets.length / 8);
  buckets.forEach((bucket, index) => {
    const center = bucketCenterMs(bucket, grain);
    const prevCenter = index ? bucketCenterMs(buckets[index - 1], grain) : null;
    const nextCenter = index < buckets.length - 1 ? bucketCenterMs(buckets[index + 1], grain) : null;
    const slotStart = index ? (prevCenter + center) / 2 : periodStart;
    const slotEnd = index < buckets.length - 1 ? (center + nextCenter) / 2 : periodEnd;
    const rectX = xForTime(slotStart);
    const rectW = Math.max(1, xForTime(slotEnd) - rectX);
    const title = `${bucketTitle(bucket, grain)}: Dials ${bucket.dials || 0}, Conversations ${bucket.conversations || 0}, Booked ${bucket.booked || 0}`;
    parts.push(`<rect x="${rectX}" y="${top}" width="${rectW}" height="${plotHeight}" fill="transparent"><title>${title}</title></rect>`);
    if (index % step && index !== buckets.length - 1) return;
    parts.push(`<text x="${xForIndex(index)}" y="${height - 6}" class="line-chart-day-label">${bucketAxisLabel(bucket, grain, buckets.length, index)}</text>`);
  });

  container.setAttribute("aria-label", "Activity chart: dials, conversations, and booked");
  container.innerHTML = `<svg width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="presentation">${parts.join("")}</svg>`;
}

export function bindPerformanceChart() {
  paintLegend(() => buildPerformanceLineChart(lastTrend));
  const resize = () => {
    if (lastTrend?.buckets?.length) buildPerformanceLineChart(lastTrend);
  };
  window.addEventListener("resize", resize);
  const container = byId("performanceLineChart");
  if (container && typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => resize());
    observer.observe(container);
  }
}
