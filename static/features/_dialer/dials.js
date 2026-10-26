import { state } from "../../_core/state.js";
import { byId, createCrmStatusSelect, crmStatusMenuOpen, setText } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { showToast } from "../../_core/notify.js";
import { formatTranscriptCsvCell, openTranscript } from "../../_core/transcript.js";
import { focusProspect } from "../_prospects/table.js";

let lastDialsSignature = null;
let dialsRenderDeferred = false;

document.addEventListener("crm-status-menu-close", (event) => {
  const select = event.detail?.select;
  if (!select || !byId("dialsTable")?.contains(select)) return;
  queueMicrotask(() => renderDials());
});

const DIALS_CSV_HEADERS = [
  "When",
  "Prospect",
  "Phone",
  "Business",
  "Reviews",
  "Call transcript",
  "Status",
  "lead_id",
  "timezone",
  "dial_id",
  "started_at",
  "ended_at",
  "caller_id",
  "answered_by",
  "duration_seconds",
  "dial_transcript_lines",
  "connected",
  "outcome",
];

function csvEscape(value) {
  const text = value == null ? "" : String(value);
  if (/[",\n\r]/.test(text)) return `"${text.replace(/"/g, '""')}"`;
  return text;
}

function dialsCsvText(rows) {
  const lines = [DIALS_CSV_HEADERS.join(",")];
  for (const { leadId, entry } of rows) {
    const lead = prospectFor(leadId);
    const connected = entry.connected;
    const connectedText = connected === true ? "true" : connected === false ? "false" : "";
    const record = [
      entry.ended_at || entry.started_at || "",
      lead?.name || "",
      lead?.phone || "",
      lead?.business || "",
      lead?.review_count ?? "",
      formatTranscriptCsvCell(lead?.transcript),
      lead?.status || "",
      leadId,
      lead?.timezone || "",
      entry.id || "",
      entry.started_at || "",
      entry.ended_at || "",
      entry.caller_id || "",
      entry.answered_by || "",
      entry.duration_seconds ?? "",
      entry.transcript_lines ?? "",
      connectedText,
      entry.outcome || "",
    ];
    lines.push(record.map(csvEscape).join(","));
  }
  return `\uFEFF${lines.join("\r\n")}`;
}

export function exportDialsCsv() {
  const button = byId("exportDialsButton");
  const rows = dialRows(state.leads);
  if (!rows.length) {
    showToast("No dials to export yet.", true);
    return;
  }
  if (button) button.disabled = true;
  try {
    const csv = dialsCsvText(rows);
    const blobUrl = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = blobUrl;
    anchor.download = "total-dials-export.csv";
    document.body.append(anchor);
    anchor.click();
    anchor.remove();
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
  } catch (error) {
    console.error("Total dials CSV export failed:", error);
    showToast(error?.message || "Export failed.", true);
  } finally {
    if (button) button.disabled = false;
  }
}

export function bindDialsExport() {
  const button = byId("exportDialsButton");
  if (button) button.addEventListener("click", exportDialsCsv);
}

export function renderDials() {
  const table = byId("dialsTable");
  if (crmStatusMenuOpen(table)) {
    dialsRenderDeferred = true;
    return;
  }
  const rows = dialRows(state.leads);
  const signature = dialsTableSignature(rows);
  setText("dialsTabCount", String(rows.length));
  setText("dialsTableSummary", `${rows.length} dial${rows.length === 1 ? "" : "s"}`);
  if (!dialsRenderDeferred && signature === lastDialsSignature) return;
  dialsRenderDeferred = false;
  lastDialsSignature = signature;
  const body = byId("dialsTableBody");
  body.replaceChildren(...rows.map(({ leadId, entry }) => {
    const lead = prospectFor(leadId);
    const row = document.createElement("tr");
    row.dataset.leadId = leadId;
    row.append(cell(dialWhen(entry.ended_at || entry.started_at)));
    row.append(prospectCell(leadId, lead));
    row.append(phoneCell(lead));
    row.append(cell(lead?.business || "—"));
    row.append(cell(reviewText(lead)));
    row.append(transcriptCell(leadId, lead));
    row.append(statusCell(lead));
    return row;
  }));
  byId("dialsTable").hidden = rows.length === 0;
  byId("dialsTableEmpty").classList.toggle("visible", rows.length === 0);
}

function prospectFor(leadId) {
  return state.leads.find((item) => item.id === leadId) || null;
}

function dialsTableSignature(rows) {
  const parts = [String(rows.length)];
  for (const { leadId, entry } of rows) {
    const lead = prospectFor(leadId);
    parts.push(
      leadId,
      entry.ended_at || entry.started_at || "",
      lead?.name || "",
      lead?.phone || "",
      lead?.business || "",
      String(lead?.review_count ?? ""),
      String(lead?.transcript?.length ?? 0),
      lead?.status || "",
      lead?.scheduled_until || "",
      state.pending_outcome?.id === leadId ? "1" : "0",
    );
  }
  return parts.join("\x1e");
}

function dialRows(leads) {
  const rows = [];
  for (const lead of leads || []) {
    if (!lead?.id) continue;
    const log = lead.call_log || [];
    for (const entry of log) rows.push({ leadId: lead.id, entry });
    if (!log.length && lead.transcript?.length) {
      const stamps = lead.transcript.map((line) => line.timestamp).filter(Boolean).sort();
      rows.push({
        leadId: lead.id,
        entry: { started_at: stamps[0] || "", ended_at: stamps.at(-1) || stamps[0] || "" },
      });
    }
  }
  rows.sort((left, right) => stamp(right).localeCompare(stamp(left)));
  return rows;
}

function stamp(row) {
  return String(row.entry.ended_at || row.entry.started_at || "");
}

function dialWhen(iso) {
  const date = new Date(iso || "");
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function reviewText(lead) {
  const count = lead?.review_count;
  if (count === 0 || count) return String(count);
  return "—";
}

function prospectCell(leadId, lead) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = "dial-prospect-link";
  const name = lead?.name || "Unnamed prospect";
  button.textContent = name;
  button.title = "Open in Prospects";
  button.addEventListener("click", () => focusProspect(leadId));
  cell.append(button);
  return cell;
}

function phoneCell(lead) {
  const cell = document.createElement("td");
  cell.className = "phone-cell";
  if (!lead?.phone) {
    cell.textContent = "—";
    return cell;
  }
  const link = document.createElement("a");
  link.className = "phone-link";
  link.href = `tel:${lead.phone}`;
  link.textContent = formatPhoneNumber(lead.phone);
  cell.append(link);
  return cell;
}

function transcriptCell(leadId, lead) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  const count = lead?.transcript?.length || 0;
  button.type = "button";
  button.className = "transcript-view-button";
  button.textContent = count ? `View · ${count}` : "No transcript";
  button.disabled = count === 0;
  button.addEventListener("click", () => {
    const current = prospectFor(leadId);
    if (current) openTranscript(current);
  });
  cell.append(button);
  return cell;
}

function statusCell(lead) {
  const cell = document.createElement("td");
  cell.className = "status-cell";
  if (lead) cell.append(createCrmStatusSelect(lead));
  else cell.textContent = "—";
  return cell;
}

function cell(text) {
  const item = document.createElement("td");
  item.textContent = text;
  return item;
}
