import { byId, dayLabel } from "../../_core/format.js";

/** Counts per bucket; same three metrics as the period cards (performance.py). */
export const PERFORMANCE_CHART_SERIES = [
  { key: "dials", label: "Dials", stroke: "#34d399", className: "line-series-dials", pointClass: "line-point-dials" },
  { key: "pickups", label: "Pickups", stroke: "#a78bfa", className: "line-series-pickups", pointClass: "line-point-pickups" },
  { key: "booked", label: "Booked", stroke: "#f472b6", className: "line-series-booked", pointClass: "line-point-booked" },
];

const SERIES = PERFORMANCE_CHART_SERIES;

let visible = { dials: true, pickups: true, booked: true };
let lastTrend = null;
let layoutRetryTimer = null;

const VIEW_WIDTH = 960;
const VIEW_HEIGHT = 320;
const PLOT_LEFT = 40;
const PLOT_RIGHT = 16;
const PLOT_TOP = 16;
const PLOT_BOTTOM = 32;
const STROKE_WIDTH = 2.5;

function hourLabel(hour) {
  return `${hour % 12 || 12}${hour < 12 ? "a" : "p"}`;
}

function bucketMetric(bucket, key) {
  if (key === "pickups") {
    const raw = bucket?.pickups ?? bucket?.conversations;
    const value = Number(raw);
    return Number.isFinite(value) ? Math.max(0, value) : 0;
  }
  const value = Number(bucket?.[key]);
  return Number.isFinite(value) ? Math.max(0, value) : 0;
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

function chartPanelHidden(container) {
  return Boolean(container.closest("[hidden]") || container.hidden);
}

function chartLayoutReady(container) {
  if (chartPanelHidden(container)) return false;
  return container.getBoundingClientRect().height >= 40;
}

function scheduleLayoutRetry() {
  if (layoutRetryTimer) return;
  layoutRetryTimer = window.setTimeout(() => {
    layoutRetryTimer = null;
    if (lastTrend?.buckets?.length) buildPerformanceLineChart(lastTrend);
  }, 50);
}

function xForBucketIndex(index, count, plotWidth) {
  if (count <= 1) return PLOT_LEFT + plotWidth / 2;
  return PLOT_LEFT + (index / (count - 1)) * plotWidth;
}

function yScaleMax(buckets) {
  let peakDials = 0;
  for (const bucket of buckets) {
    peakDials = Math.max(peakDials, bucketMetric(bucket, "dials"));
  }
  if (peakDials <= 0) return 1;
  return Math.max(1, Math.ceil(peakDials * 1.1));
}

function linePath(points) {
  if (!points.length) return "";
  const [first, ...rest] = points;
  return `M ${first.x} ${first.y}${rest.map((point) => ` L ${point.x} ${point.y}`).join("")}`;
}

export function buildPerformanceLineChart(trend) {
  const container = byId("performanceLineChart");
  const empty = byId("performanceChartEmpty");
  if (!container || !empty) return;
  const buckets = trend?.buckets || [];
  const grain = trend?.grain || "day";
  lastTrend = trend;
  const hasData = buckets.length > 0;
  const hiddenPanel = chartPanelHidden(container);
  if (!hiddenPanel) {
    empty.hidden = hasData;
    container.hidden = !hasData;
  }
  if (!hasData) {
    if (!hiddenPanel) {
      container.textContent = "";
      container.setAttribute("aria-label", "No activity in this range");
    }
    return;
  }
  if (hiddenPanel) return;
  if (!chartLayoutReady(container)) {
    scheduleLayoutRetry();
    return;
  }

  const width = VIEW_WIDTH;
  const height = VIEW_HEIGHT;
  const plotWidth = width - PLOT_LEFT - PLOT_RIGHT;
  const plotHeight = height - PLOT_TOP - PLOT_BOTTOM;
  const plotBottom = PLOT_TOP + plotHeight;
  const yMax = yScaleMax(buckets);
  const { start: periodStart, end: periodEnd } = periodBounds(trend, buckets, grain);
  const span = Math.max(periodEnd - periodStart, 1);
  const xForTime = (ms) => {
    const clamped = Math.min(periodEnd, Math.max(periodStart, ms));
    return PLOT_LEFT + ((clamped - periodStart) / span) * plotWidth;
  };
  const yFor = (value) => {
    const n = Number(value);
    const safe = Number.isFinite(n) ? Math.max(0, n) : 0;
    return plotBottom - (safe / yMax) * plotHeight;
  };

  const chrome = [];
  const overlays = [];
  const seriesParts = [];
  const labels = [];

  chrome.push(`<clipPath id="performance-plot-clip"><rect x="${PLOT_LEFT}" y="${PLOT_TOP}" width="${plotWidth}" height="${plotHeight}" /></clipPath>`);
  chrome.push(`<line x1="${PLOT_LEFT}" y1="${PLOT_TOP}" x2="${PLOT_LEFT}" y2="${plotBottom}" class="line-chart-axis-edge" />`);
  chrome.push(`<line x1="${width - PLOT_RIGHT}" y1="${PLOT_TOP}" x2="${width - PLOT_RIGHT}" y2="${plotBottom}" class="line-chart-axis-edge" />`);
  chrome.push(`<line x1="${PLOT_LEFT}" y1="${plotBottom}" x2="${width - PLOT_RIGHT}" y2="${plotBottom}" class="line-chart-axis-edge" />`);

  for (const fraction of [0, 0.5, 1]) {
    const y = plotBottom - plotHeight * fraction;
    const gridClass = fraction === 0 ? "line-chart-axis-baseline" : "line-chart-grid";
    chrome.push(`<line x1="${PLOT_LEFT}" y1="${y}" x2="${width - PLOT_RIGHT}" y2="${y}" class="${gridClass}" />`);
    chrome.push(`<text x="${PLOT_LEFT - 8}" y="${y + 4}" class="line-chart-y-label">${Math.round(yMax * fraction)}</text>`);
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
    const title = `${bucketTitle(bucket, grain)}: Dials ${bucketMetric(bucket, "dials")}, Pickups ${bucketMetric(bucket, "pickups")}, Booked ${bucketMetric(bucket, "booked")}`;
    overlays.push(`<rect x="${rectX}" y="${PLOT_TOP}" width="${rectW}" height="${plotHeight}" fill="transparent" pointer-events="all"><title>${title}</title></rect>`);
    if (index % step && index !== buckets.length - 1) return;
    const x = xForBucketIndex(index, buckets.length, plotWidth);
    labels.push(`<text x="${x}" y="${height - 8}" class="line-chart-day-label">${bucketAxisLabel(bucket, grain, buckets.length, index)}</text>`);
  });

  const drawOrder = ["dials", "booked", "pickups"];
  seriesParts.push(`<g clip-path="url(#performance-plot-clip)">`);
  for (const key of drawOrder) {
    const series = SERIES.find((item) => item.key === key);
    if (!series || !visible[series.key]) continue;
    const points = buckets.map((bucket, index) => ({
      x: xForBucketIndex(index, buckets.length, plotWidth),
      y: yFor(bucketMetric(bucket, series.key)),
    }));
    const strokeWidth = series.key === "pickups" ? 3 : STROKE_WIDTH;
    const dash = series.key === "pickups" ? ' stroke-dasharray="8 5"' : "";
    seriesParts.push(
      `<path d="${linePath(points)}" class="line-series ${series.className}" fill="none" stroke="${series.stroke}" stroke-width="${strokeWidth}" stroke-linecap="round" stroke-linejoin="round"${dash} />`,
    );
  }
  seriesParts.push("</g>");

  container.setAttribute("aria-label", "Activity chart: dials, pickups, and booked");
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="xMidYMid meet" role="presentation" xmlns="http://www.w3.org/2000/svg">${chrome.join("")}${overlays.join("")}${seriesParts.join("")}${labels.join("")}</svg>`;
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
  const panel = byId("metricsPanel");
  if (panel && typeof MutationObserver !== "undefined") {
    const visibility = new MutationObserver(() => {
      if (!panel.hidden) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => resize());
        });
      }
    });
    visibility.observe(panel, { attributes: true, attributeFilter: ["hidden"] });
  }
}
