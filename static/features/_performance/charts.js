import { STATUS_COLOR_VARS, STATUS_KEYS, STATUS_LABELS, byId } from "../../core.js";

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
