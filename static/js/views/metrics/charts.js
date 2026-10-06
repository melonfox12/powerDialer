import { STATUS_COLOR_VARS, STATUS_KEYS, STATUS_LABELS, byId, dayLabel } from "../../utils/format.js";

export function buildMetricsLineChart(series) {
  const container = byId("metricsLineChart");
  const hasActivity = series.some((day) => (day.dials || 0) > 0 || (day.connected || 0) > 0);
  const panel = container.closest(".performance-chart-panel");
  panel.classList.toggle("has-no-data", !hasActivity);
  if (!hasActivity) {
    container.textContent = "No call activity in the last 7 days.";
    container.setAttribute("aria-label", "No call activity in the last 7 days");
    return;
  }
  container.setAttribute("aria-label", "Dials and connected calls trend over the last 7 days");
  const width = 620;
  const height = 190;
  const left = 36;
  const right = 10;
  const top = 12;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maxValue = Math.max(1, ...series.map((day) => Math.max(day.dials || 0, day.connected || 0)));
  const xFor = (index) => left + index * plotWidth / Math.max(1, series.length - 1);
  const yFor = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const svgParts = [];

  for (let step = 0; step <= 2; step += 1) {
    const value = Math.round(maxValue * (2 - step) / 2);
    const y = top + plotHeight * step / 2;
    svgParts.push(`<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="line-chart-gridline" />`);
    svgParts.push(`<text x="${left - 8}" y="${y + 3}" class="line-chart-axis-label">${value}</text>`);
  }

  for (const metric of ["dials", "connected"]) {
    const points = series.map((day, index) => `${xFor(index)},${yFor(day[metric] || 0)}`);
    svgParts.push(`<polyline points="${points.join(" ")}" class="line-series line-series-${metric}" />`);
    series.forEach((day, index) => {
      svgParts.push(`<circle cx="${xFor(index)}" cy="${yFor(day[metric] || 0)}" r="3" class="line-point line-point-${metric}"><title>${dayLabel(day.date)}: ${day[metric] || 0} ${metric}</title></circle>`);
    });
  }

  series.forEach((day, index) => {
    svgParts.push(`<text x="${xFor(index)}" y="${height - 7}" class="line-chart-day-label">${dayLabel(day.date)}</text>`);
  });
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="presentation">${svgParts.join("")}</svg>`;
}

export function pieSlicePath(cx, cy, radius, startAngle, endAngle) {
  const startRadians = startAngle * Math.PI / 180;
  const endRadians = endAngle * Math.PI / 180;
  const startX = cx + radius * Math.cos(startRadians);
  const startY = cy + radius * Math.sin(startRadians);
  const endX = cx + radius * Math.cos(endRadians);
  const endY = cy + radius * Math.sin(endRadians);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M${cx},${cy} L${startX},${startY} A${radius},${radius} 0 ${largeArc} 1 ${endX},${endY} Z`;
}

export function buildStatusPieChart(leads) {
  const chart = byId("statusPieChart");
  const legend = byId("statusPieLegend");
  const statuses = STATUS_KEYS;
  const counts = Object.fromEntries(statuses.map((status) => [status, 0]));
  for (const lead of leads) {
    if (Object.hasOwn(counts, lead.status)) counts[lead.status] += 1;
  }
  const total = leads.length;
  const center = 76;
  const radius = 66;
  let angle = -90;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No prospects</text>`);
  } else {
    const visible = statuses.filter((status) => counts[status] > 0);
    if (visible.length === 1) {
      slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${STATUS_COLOR_VARS[visible[0]]})"><title>${STATUS_LABELS[visible[0]]}: ${counts[visible[0]]}</title></circle>`);
    } else {
      for (const status of visible) {
        const nextAngle = angle + counts[status] / total * 360;
        slices.push(`<path d="${pieSlicePath(center, center, radius, angle, nextAngle)}" fill="var(${STATUS_COLOR_VARS[status]})" stroke="var(--paper)" stroke-width="2"><title>${STATUS_LABELS[status]}: ${counts[status]}</title></path>`);
        angle = nextAngle;
      }
    }
  }

  chart.setAttribute("aria-label", `Prospects by status, ${total} total`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...statuses.map((status) => {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch status-pie-${status}`;
    const label = document.createElement("span");
    label.textContent = STATUS_LABELS[status];
    const value = document.createElement("strong");
    const percent = total ? Math.round(counts[status] / total * 100) : 0;
    value.textContent = `${counts[status]} · ${percent}%`;
    item.append(swatch, label, value);
    return item;
  }));
}

export function buildConnectionPieChart(allTime) {
  const chart = byId("connectionPieChart");
  const legend = byId("connectionPieLegend");
  const total = Math.max(0, Number(allTime.dials) || 0);
  const connected = Math.min(total, Math.max(0, Number(allTime.connected) || 0));
  const notConnected = total - connected;
  const center = 76;
  const radius = 66;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No dials</text>`);
  } else if (!connected || !notConnected) {
    const color = connected ? "--success" : "--amber";
    const label = connected ? "Connected" : "Not connected";
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${color})"><title>${label}: ${total}</title></circle>`);
  } else {
    const splitAngle = -90 + connected / total * 360;
    slices.push(`<path d="${pieSlicePath(center, center, radius, -90, splitAngle)}" fill="var(--success)" stroke="var(--paper)" stroke-width="2"><title>Connected: ${connected}</title></path>`);
    slices.push(`<path d="${pieSlicePath(center, center, radius, splitAngle, 270)}" fill="var(--amber)" stroke="var(--paper)" stroke-width="2"><title>Not connected: ${notConnected}</title></path>`);
  }

  chart.setAttribute("aria-label", `Dial outcomes: ${connected} connected and ${notConnected} not connected`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...[
    { label: "Connected", count: connected, className: "connection-connected" },
    { label: "Not connected", count: notConnected, className: "connection-unconnected" },
  ].map((item) => {
    const row = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch ${item.className}`;
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    const percent = total ? Math.round(item.count / total * 100) : 0;
    value.textContent = `${item.count} · ${percent}%`;
    row.append(swatch, label, value);
    return row;
  }));
}
