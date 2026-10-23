import { byId, dayLabel, formatRate } from "../../_core/format.js";

const WIDTH = 620;
const LEFT = 38;
const RIGHT = 10;
const MARKER_Y = 8;
const RATE_TOP = 22;
const RATE_HEIGHT = 92;
const BAR_TOP = 128;
const BAR_HEIGHT = 34;
const LABEL_Y = 186;
const HEIGHT = 196;
const MAX_LABELS = 8;
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

function shortDate(dateStr) {
  const [, month, day] = dateStr.split("-");
  return `${Number(month)}/${Number(day)}`;
}

function hourLabel(hour) {
  return `${hour % 12 || 12}${hour < 12 ? "a" : "p"}`;
}

function bucketLabel(bucket, grain, count) {
  if (grain === "hour") return hourLabel(bucket.hour);
  if (grain === "week" || count > MAX_LABELS) return shortDate(bucket.date);
  return dayLabel(bucket.date);
}

function bucketTitle(bucket, grain) {
  if (grain === "hour") return `${hourLabel(bucket.hour)}`;
  const date = new Date(`${bucket.date}T00:00:00Z`);
  const text = date.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
  return grain === "week" ? `Week of ${text}` : text;
}

function plural(count, word) {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

// Connect rate on its own 0..max% scale, daily dial volume as bars under it, booked meetings as markers above it.
export function buildTrendChart(trend) {
  const container = byId("metricsLineChart");
  const buckets = trend?.buckets || [];
  const grain = trend?.grain || "day";
  const dials = buckets.reduce((sum, bucket) => sum + bucket.dials, 0);
  const booked = buckets.reduce((sum, bucket) => sum + bucket.booked, 0);
  if (!dials && !booked) {
    container.textContent = "No calls in this range yet.";
    container.setAttribute("aria-label", "No calls in this range yet");
    return;
  }
  const connected = buckets.reduce((sum, bucket) => sum + bucket.connected, 0);
  container.setAttribute(
    "aria-label",
    `Connect rate over time: ${connected} of ${plural(dials, "dial")} connected, ${plural(booked, "meeting")} booked`,
  );
  const plotWidth = WIDTH - LEFT - RIGHT;
  const slot = plotWidth / buckets.length;
  const xFor = (index) => LEFT + (index + 0.5) * slot;
  const topRate = Math.max(0.1, Math.min(1, Math.ceil(Math.max(0, ...buckets.map((bucket) => bucket.rate ?? 0)) * 10) / 10));
  const yFor = (rate) => RATE_TOP + RATE_HEIGHT - (rate / topRate) * RATE_HEIGHT;
  const maxDials = Math.max(1, ...buckets.map((bucket) => bucket.dials));
  const parts = [];

  for (const fraction of [0, 0.5, 1]) {
    const y = yFor(topRate * fraction);
    parts.push(`<line x1="${LEFT}" y1="${y}" x2="${WIDTH - RIGHT}" y2="${y}" class="line-chart-gridline" />`);
    parts.push(`<text x="${LEFT - 6}" y="${y + 3}" class="line-chart-axis-label">${formatRate(topRate * fraction)}</text>`);
  }

  const barWidth = Math.max(2, Math.min(28, slot * 0.6));
  buckets.forEach((bucket, index) => {
    if (!bucket.dials) return;
    const height = Math.max(1, bucket.dials / maxDials * BAR_HEIGHT);
    parts.push(`<rect x="${xFor(index) - barWidth / 2}" y="${BAR_TOP + BAR_HEIGHT - height}" width="${barWidth}" height="${height}" rx="1.5" class="perf-bar"><title>${bucketTitle(bucket, grain)}: ${plural(bucket.dials, "dial")}</title></rect>`);
  });
  parts.push(`<text x="${LEFT - 6}" y="${BAR_TOP + 8}" class="line-chart-axis-label">${maxDials}</text>`);
  parts.push(`<text x="${LEFT - 6}" y="${BAR_TOP + BAR_HEIGHT}" class="line-chart-axis-label">0</text>`);

  let run = [];
  const flush = () => {
    if (run.length > 1) parts.push(`<polyline points="${run.join(" ")}" class="line-series line-series-connected" />`);
    run = [];
  };
  buckets.forEach((bucket, index) => {
    if (bucket.rate === null) {
      flush();
      return;
    }
    run.push(`${xFor(index)},${yFor(bucket.rate)}`);
  });
  flush();
  const radius = buckets.length > 20 ? 2 : 3;
  buckets.forEach((bucket, index) => {
    if (bucket.rate === null) return;
    parts.push(`<circle cx="${xFor(index)}" cy="${yFor(bucket.rate)}" r="${radius}" class="line-point line-point-connected"><title>${bucketTitle(bucket, grain)}: ${formatRate(bucket.rate)} connect rate (${bucket.connected} of ${plural(bucket.dials, "dial")})</title></circle>`);
  });

  buckets.forEach((bucket, index) => {
    if (!bucket.booked) return;
    const x = xFor(index);
    parts.push(`<path d="M${x},${MARKER_Y - 5} L${x + 5},${MARKER_Y} L${x},${MARKER_Y + 5} L${x - 5},${MARKER_Y} Z" class="perf-marker"><title>${bucketTitle(bucket, grain)}: ${plural(bucket.booked, "meeting")} booked</title></path>`);
  });

  const step = Math.ceil(buckets.length / MAX_LABELS);
  buckets.forEach((bucket, index) => {
    if (index % step) return;
    parts.push(`<text x="${xFor(index)}" y="${LABEL_Y}" class="line-chart-day-label">${bucketLabel(bucket, grain, buckets.length)}</text>`);
  });
  container.innerHTML = `<svg viewBox="0 0 ${WIDTH} ${HEIGHT}" role="presentation">${parts.join("")}</svg>`;
}

export function buildOutcomeBar(outcomes) {
  const bar = byId("outcomeBar");
  const legend = byId("outcomeLegend");
  const note = byId("outcomeNote");
  const items = outcomes?.items || [];
  note.hidden = items.length > 0;
  note.textContent = "No tagged calls in this range. Tag a connected call after you talk and the split shows up here.";
  bar.hidden = items.length === 0;
  bar.setAttribute("aria-label", items.length
    ? `Share of tagged calls: ${items.map((item) => `${item.label} ${formatRate(item.share)}`).join(", ")}`
    : "No tagged calls in this range");
  bar.replaceChildren(...items.map((item) => {
    const segment = document.createElement("span");
    segment.className = `perf-outcome-seg perf-outcome-${item.key}`;
    segment.style.width = `${item.share * 100}%`;
    segment.title = `${item.label}: ${item.count} (${formatRate(item.share)})`;
    return segment;
  }));
  legend.replaceChildren(...items.map((item) => {
    const row = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch perf-outcome-${item.key}`;
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    value.textContent = `${item.count} · ${formatRate(item.share)}`;
    row.append(swatch, label, value);
    return row;
  }));
}

// Weekday rows by hour columns. Cells under the minimum dial count are muted, not colored.
export function buildHeatmap(heatmap) {
  const grid = byId("heatmapGrid");
  const note = byId("heatmapNote");
  if (!heatmap?.unlocked) {
    grid.hidden = true;
    grid.replaceChildren();
    note.hidden = false;
    note.textContent = `Unlocks after ${heatmap?.unlock_at ?? 100} dials (${heatmap?.total_dials ?? 0} so far).`;
    return;
  }
  note.hidden = false;
  note.textContent = `Colored cells have at least ${heatmap.min_bucket_dials} dials. Dim cells have fewer, so read them as a hint.`;
  grid.hidden = false;
  const cells = new Map(heatmap.cells.map((cell) => [`${cell.weekday}:${cell.hour}`, cell]));
  const hours = heatmap.cells.map((cell) => cell.hour);
  const first = Math.min(8, ...hours);
  const last = Math.max(18, ...hours);
  const bestRate = Math.max(0, ...heatmap.cells.filter((cell) => cell.qualified).map((cell) => cell.rate ?? 0));
  grid.style.gridTemplateColumns = `auto repeat(${last - first + 1}, minmax(0, 1fr))`;
  const nodes = [document.createElement("span")];
  for (let hour = first; hour <= last; hour += 1) {
    const head = document.createElement("span");
    head.className = "perf-heat-head";
    head.textContent = hourLabel(hour);
    nodes.push(head);
  }
  WEEKDAYS.forEach((name, weekday) => {
    const label = document.createElement("span");
    label.className = "perf-heat-head perf-heat-day";
    label.textContent = name;
    nodes.push(label);
    for (let hour = first; hour <= last; hour += 1) {
      const cell = cells.get(`${weekday}:${hour}`);
      const node = document.createElement("span");
      node.className = "perf-cell";
      if (cell) {
        const text = `${name} ${hourLabel(hour)}: ${cell.dials} dials, ${cell.connects} connects, ${formatRate(cell.rate)}`;
        node.setAttribute("role", "img");
        node.setAttribute("aria-label", text);
        node.title = text;
        if (cell.qualified) {
          node.classList.add("perf-cell-hot");
          node.style.setProperty("--heat", String(bestRate ? 0.2 + 0.8 * (cell.rate ?? 0) / bestRate : 0.2));
          node.textContent = String(Math.round((cell.rate ?? 0) * 100));
        } else {
          node.classList.add("perf-cell-muted");
        }
      }
      nodes.push(node);
    }
  });
  grid.replaceChildren(...nodes);
}
