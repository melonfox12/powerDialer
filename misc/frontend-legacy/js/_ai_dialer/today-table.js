import { state } from "../../_core/state.js";
import { AGENT_USE_STATUS, CRM_STATUS_LABELS, STATUS_STYLES, agentUseStatusText, byId } from "../../_core/format.js";
import { openTranscript, segmentsForDial, transcriptTimestamp } from "../../_core/transcript.js";
import { locationText } from "../_prospects/query.js";
import { primaryAgent } from "./agents.js";

function isTodayIso(iso) {
  if (!iso) return false;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return false;
  const now = new Date();
  return (
    date.getFullYear() === now.getFullYear()
    && date.getMonth() === now.getMonth()
    && date.getDate() === now.getDate()
  );
}

function todayDialRows() {
  const rows = [];
  for (const lead of state.leads || []) {
    if (!lead?.id) continue;
    const log = lead.call_log || [];
    for (const entry of log) {
      const when = entry.ended_at || entry.started_at || "";
      if (isTodayIso(when)) rows.push({ lead, entry });
    }
  }
  rows.sort((left, right) => {
    const a = right.entry.ended_at || right.entry.started_at || "";
    const b = left.entry.ended_at || left.entry.started_at || "";
    return a.localeCompare(b);
  });
  return rows;
}

function statusLabel(lead, entry) {
  const status = lead?.status || "new";
  const label = status === AGENT_USE_STATUS
    ? agentUseStatusText(lead)
    : (CRM_STATUS_LABELS[status] || STATUS_STYLES[status]?.label || status);
  if (status === "dialed" && lead?.scheduled_until) {
    const time = transcriptTimestamp(lead.scheduled_until).replace(/:\d{2}$/, "");
    return `${label} · callback ${time}`;
  }
  if (entry?.connected) return `${label} · connected`;
  if (entry?.answered_by === "voicemail") return `${label} · voicemail`;
  if (entry?.answered_by) return `${label} (${entry.answered_by.replace(/_/g, " ")})`;
  return label;
}

function transcriptPreview(lead, entry) {
  const lines = segmentsForDial(lead, entry);
  if (!lines.length) {
    const count = lead?.transcript?.length || 0;
    if (!count) return "No transcript yet";
    const last = lead.transcript[lead.transcript.length - 1];
    const text = String(last?.text || "").trim();
    return text.length > 72 ? `${text.slice(0, 69)}…` : text || "View transcript";
  }
  const last = lines[lines.length - 1];
  const text = String(last?.text || "").trim();
  return text.length > 72 ? `${text.slice(0, 69)}…` : text || "View transcript";
}

function placeCell(lead) {
  const city = locationText(lead, "city");
  const region = locationText(lead, "state");
  const county = locationText(lead, "county");
  const parts = [county, region, city].map((part) => String(part || "").trim()).filter(Boolean);
  if (!parts.length) return "—";
  const unique = [];
  for (const part of parts) {
    if (!unique.includes(part)) unique.push(part);
  }
  return unique.join(" / ");
}

let lastSignature = "";

export function renderTodayDialTable(agentId) {
  const body = byId("aiDialerAgent-todayDialsBody");
  const caption = byId("aiDialerAgent-todayDialsCaption");
  if (!body) return;
  const agent = primaryAgent();
  if (agentId && agentId !== agent.id) {
    body.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "ai-today-empty";
    cell.textContent = "This agent seat is not linked to a dialer session yet.";
    row.append(cell);
    body.append(row);
    if (caption) caption.textContent = "Prospects dialed today";
    return;
  }
  const rows = todayDialRows();
  const signature = rows.map(({ lead, entry }) => [
    lead.id,
    entry.id || "",
    entry.ended_at || entry.started_at || "",
    lead.status,
    lead.transcript?.length || 0,
    segmentsForDial(lead, entry).length,
  ].join("|")).join("\x1e");
  if (signature === lastSignature) return;
  lastSignature = signature;
  body.replaceChildren();
  if (caption) {
    caption.textContent = rows.length
      ? `Prospects dialed today · ${rows.length}`
      : "Prospects dialed today";
  }
  if (!rows.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 5;
    cell.className = "ai-today-empty";
    cell.textContent = "No dials logged yet today. Start this agent to populate the board.";
    row.append(cell);
    body.append(row);
    return;
  }
  for (const { lead, entry } of rows) {
    const row = document.createElement("tr");
  row.dataset.leadId = lead.id;
    const name = document.createElement("td");
    name.textContent = lead.name || "—";
    const business = document.createElement("td");
    business.textContent = lead.business || "—";
    const status = document.createElement("td");
    status.className = "ai-today-status";
    status.textContent = statusLabel(lead, entry);
    const transcript = document.createElement("td");
    const transcriptBtn = document.createElement("button");
    transcriptBtn.type = "button";
    transcriptBtn.className = "ai-transcript-preview";
    transcriptBtn.textContent = transcriptPreview(lead, entry);
    transcriptBtn.addEventListener("click", () => {
      const segments = segmentsForDial(lead, entry);
      openTranscript({
        ...lead,
        transcript: segments.length ? segments : lead.transcript || [],
      });
    });
    transcript.append(transcriptBtn);
    const place = document.createElement("td");
    place.textContent = placeCell(lead);
    row.append(name, business, status, transcript, place);
    body.append(row);
  }
}
