import { byId, dayLabel, formatRate } from "../../_core/format.js";

const SERIES = [
  { key: "dials", label: "Dials", className: "line-series-dials", pointClass: "line-point-dials", marker: false },
  { key: "conversations", label: "Conversations", className: "line-series-connected", pointClass: "line-point-connected", marker: true },
  { key: "booked", label: "Booked", className: "line-series-booked", pointClass: "line-point-booked", marker: true },
];

let visible = { dials: true, conversations: true, booked: true };
let lastBuckets = [];
let lastGrain = "day";

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

function bucketAxisLabel(bucket, grain, count) {
  if (grain === "hour") return hourLabel(bucket.hour);
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

function chartSize(container) {
  const hidden = container.closest("[hidden]") || container.hidden;
  if (hidden) return { width: 640, height: 220 };
  const rect = container.getBoundingClientRect();
  const width = Math.round(rect.width) || container.clientWidth || 640;
  const height = Math.round(rect.height) || container.clientHeight || 220;
  return { width: Math.max(width, 280), height: Math.max(height, 120) };
}

export function buildPerformanceLineChart(trend) {
  const container = byId("performanceLineChart");
  const empty = byId("performanceChartEmpty");
  if (!container || !empty) return;
  const buckets = trend?.buckets || [];
  lastBuckets = buckets;
  lastGrain = trend?.grain || "day";
  const hasData = buckets.some((bucket) => bucket.dials || bucket.conversations || bucket.booked);
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
  const maxValue = Math.max(1, ...buckets.flatMap((bucket) => [bucket.dials, bucket.conversations, bucket.booked]));
  const xFor = (index) => left + (index + 0.5) * (plotWidth / buckets.length);
  const yFor = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const parts = [];

  for (const fraction of [0, 0.5, 1]) {
    const y = top + plotHeight * (1 - fraction);
    parts.push(`<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="line-chart-gridline" />`);
    parts.push(`<text x="${left - 6}" y="${y + 3}" class="line-chart-axis-label">${Math.round(maxValue * fraction)}</text>`);
  }

  for (const series of SERIES) {
    if (!visible[series.key]) continue;
    const points = buckets.map((bucket, index) => `${xFor(index)},${yFor(bucket[series.key] || 0)}`);
    parts.push(`<polyline points="${points.join(" ")}" class="line-series ${series.className}" />`);
    if (series.marker) {
      buckets.forEach((bucket, index) => {
        const value = bucket[series.key] || 0;
        parts.push(`<circle cx="${xFor(index)}" cy="${yFor(value)}" r="3" class="line-point ${series.pointClass}"><title>${bucketTitle(bucket, lastGrain)}: ${series.label} ${value}</title></circle>`);
      });
    }
  }

  const step = Math.ceil(buckets.length / 8);
  buckets.forEach((bucket, index) => {
    const slot = plotWidth / buckets.length;
    const title = `${bucketTitle(bucket, lastGrain)}: Dials ${bucket.dials || 0}, Conversations ${bucket.conversations || 0}, Booked ${bucket.booked || 0}`;
    parts.push(`<rect x="${xFor(index) - slot / 2}" y="${top}" width="${slot}" height="${plotHeight}" fill="transparent"><title>${title}</title></rect>`);
    if (index % step) return;
    parts.push(`<text x="${xFor(index)}" y="${height - 6}" class="line-chart-day-label">${bucketAxisLabel(bucket, lastGrain, buckets.length)}</text>`);
  });

  container.setAttribute("aria-label", "Activity chart: dials, conversations, and booked");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="presentation">${parts.join("")}</svg>`;
}

export function bindPerformanceChart() {
  paintLegend(() => buildPerformanceLineChart({ grain: lastGrain, buckets: lastBuckets }));
  const resize = () => {
    if (lastBuckets.length) buildPerformanceLineChart({ grain: lastGrain, buckets: lastBuckets });
  };
  window.addEventListener("resize", resize);
  const container = byId("performanceLineChart");
  if (container && typeof ResizeObserver !== "undefined") {
    const observer = new ResizeObserver(() => resize());
    observer.observe(container);
  }
}
