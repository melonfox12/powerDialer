import { request } from "../../_core/api.js";
import { state } from "../../_core/state.js";
import { applyLeadsCatalog, applyMutationPayload, fetchLeadsCatalog } from "../../_core/sync-state.js";
import { byId, createCrmStatusSelect, crmStatusOptionText, crmStatusMenuOpen, setText } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { showToast } from "../../_core/notify.js";
import { formatTranscriptCsvCell, openTranscript } from "../../_core/transcript.js";
import { render } from "../../core.js";
import { focusProspect } from "../_prospects/table.js";
import { locationText } from "../_prospects/query.js";

let lastDialsSignature = null;
let dialsRenderDeferred = false;
let dialsRefreshBusy = false;

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
  for (const { leadId, entry, archivedRecord } of rows) {
    const lead = prospectFor(leadId, archivedRecord);
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

export async function importDialsCsv(file) {
  if (!file) return;
  const button = byId("importDialsButton");
  button.disabled = true;
  button.textContent = "Importing…";
  try {
    const result = await request("/api/dials/import", {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
    await applyMutationPayload(result);
    applyLeadsCatalog(await fetchLeadsCatalog());
    const imported = result.import || {};
    const added = imported.added || 0;
    if (!added) {
      showToast(imported.skipped ? "No new dial rows were added." : "No dial rows were found in that file.", true);
      return;
    }
    const extra = imported.skipped ? ` · ${imported.skipped} duplicate${imported.skipped === 1 ? "" : "s"} skipped` : "";
    showToast(`${added} dial row${added === 1 ? "" : "s"} imported${extra}`);
    render();
  } catch (error) {
    console.error("Total dials CSV import failed:", error);
    showToast(error?.message || "Import failed.", true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span class="button-symbol" aria-hidden="true">↑</span>Import CSV';
    byId("dialsCsvInput").value = "";
  }
}

export function exportDialsCsv() {
  const button = byId("exportDialsButton");
  const rows = dialRows(state.leads, state.archived_dials);
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

/** Reload CRM catalog and repaint Total dials (matches each row to live CRM status). */
export async function refreshDialsTab() {
  lastDialsSignature = null;
  if (dialsRefreshBusy) return;
  dialsRefreshBusy = true;
  try {
    applyLeadsCatalog(await fetchLeadsCatalog());
  } catch (error) {
    console.error("Total dials CRM refresh failed:", error);
  } finally {
    dialsRefreshBusy = false;
  }
  render();
}

export function bindDialsExport() {
  byId("importDialsButton")?.addEventListener("click", () => byId("dialsCsvInput")?.click());
  byId("dialsCsvInput")?.addEventListener("change", (event) => {
    const file = event.target.files?.[0];
    if (file) importDialsCsv(file);
  });
  const button = byId("exportDialsButton");
  if (button) button.addEventListener("click", exportDialsCsv);
}

export function renderDials() {
  const table = byId("dialsTable");
  if (crmStatusMenuOpen(table)) {
    dialsRenderDeferred = true;
    return;
  }
  const rows = dialRows(state.leads, state.archived_dials);
  const signature = dialsTableSignature(rows);
  setText("dialsTabCount", String(rows.length));
  setText("dialsTableSummary", `${rows.length} dial${rows.length === 1 ? "" : "s"}`);
  if (!dialsRenderDeferred && signature === lastDialsSignature) return;
  dialsRenderDeferred = false;
  lastDialsSignature = signature;
  const body = byId("dialsTableBody");
  body.replaceChildren(...rows.map(({ leadId, entry, archivedRecord }) => {
    const resolved = resolveDialCrmLead(leadId, archivedRecord);
    const { crmLead, snapshot, crmDeleted, focusId } = resolved;
    const displayLead = crmLead || snapshot;
    const row = document.createElement("tr");
    row.dataset.leadId = leadId;
    if (crmDeleted) row.classList.add("dials-row--removed");
    row.append(cell(dialWhen(entry.ended_at || entry.started_at)));
    row.append(prospectCell(focusId, displayLead, crmDeleted));
    row.append(phoneCell(displayLead));
    row.append(cell(displayLead?.business || "—"));
    row.append(cell(reviewText(displayLead)));
    row.append(transcriptCell(focusId, displayLead));
    row.append(statusCell(crmLead, snapshot, crmDeleted));
    return row;
  }));
  byId("dialsTable").hidden = rows.length === 0;
  byId("dialsTableEmpty").classList.toggle("visible", rows.length === 0);
}

function archivedLead(record) {
  if (!record) return null;
  return {
    id: record.lead_id || "",
    name: record.name || "",
    phone: record.phone || "",
    business: record.business || "",
    review_count: record.review_count,
    timezone: record.timezone || "",
    status: record.status || "new",
    transcript: record.transcript || [],
  };
}

function prospectFor(leadId, archivedRecord) {
  return state.leads.find((item) => item.id === leadId) || archivedLead(archivedRecord);
}

function foldText(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizePhone(raw) {
  const text = String(raw || "").trim();
  const digits = text.replace(/\D/g, "");
  if (text.startsWith("+") && digits.length >= 8 && digits.length <= 15) return `+${digits}`;
  if (digits.length === 10) return `+1${digits}`;
  if (digits.length === 11 && digits.startsWith("1")) return `+${digits}`;
  return null;
}

function dialIdentityKey(lead) {
  const name = foldText(lead?.name);
  if (!name) return null;
  const city = foldText(locationText(lead, "city"));
  const stateName = foldText(locationText(lead, "state"));
  const place = city || stateName ? `${city}\x1f${stateName}` : `\x1f${foldText(lead?.timezone)}`;
  return `${name}\x1f${place}`;
}

function resolveDialCrmLead(leadId, archivedRecord) {
  const snapshot = prospectFor(leadId, archivedRecord);
  const byId = state.leads.find((item) => item.id === leadId);
  if (byId) {
    return { crmLead: byId, snapshot, crmDeleted: false, focusId: byId.id };
  }
  const phone = normalizePhone(snapshot?.phone);
  if (phone) {
    const matches = state.leads.filter((item) => normalizePhone(item.phone) === phone);
    if (matches.length === 1) {
      return { crmLead: matches[0], snapshot, crmDeleted: false, focusId: matches[0].id };
    }
  }
  const key = dialIdentityKey(snapshot);
  if (key) {
    const matches = state.leads.filter((item) => dialIdentityKey(item) === key);
    if (matches.length === 1) {
      return { crmLead: matches[0], snapshot, crmDeleted: false, focusId: matches[0].id };
    }
  }
  return { crmLead: null, snapshot, crmDeleted: true, focusId: leadId };
}

function dialsTableSignature(rows) {
  const parts = [String(rows.length)];
  for (const { leadId, entry, archivedRecord } of rows) {
    const { crmLead, snapshot, crmDeleted } = resolveDialCrmLead(leadId, archivedRecord);
    const statusLead = crmLead || snapshot;
    parts.push(
      leadId,
      crmDeleted ? "0" : "1",
      crmLead?.id || "",
      entry.ended_at || entry.started_at || "",
      statusLead?.name || "",
      statusLead?.phone || "",
      statusLead?.business || "",
      String(statusLead?.review_count ?? ""),
      String(statusLead?.transcript?.length ?? 0),
      statusLead?.status || "",
      statusLead?.scheduled_until || "",
      state.pending_outcome?.id === (crmLead?.id || leadId) ? "1" : "0",
    );
  }
  return parts.join("\x1e");
}

function dialRows(leads, archivedRecords) {
  const rows = [];
  const archivedKeys = new Set();
  for (const lead of leads || []) {
    if (!lead?.id) continue;
    const log = lead.call_log || [];
    for (const entry of log) rows.push({ leadId: lead.id, entry, archivedRecord: null });
    if (!log.length && lead.transcript?.length) {
      const stamps = lead.transcript.map((line) => line.timestamp).filter(Boolean).sort();
      rows.push({
        leadId: lead.id,
        entry: { started_at: stamps[0] || "", ended_at: stamps.at(-1) || stamps[0] || "" },
        archivedRecord: null,
      });
    }
  }
  for (const record of archivedRecords || []) {
    const entry = record.entry || {};
    const key = `${record.lead_id || ""}\x1e${entry.id || ""}\x1e${entry.started_at || entry.ended_at || ""}`;
    if (archivedKeys.has(key)) continue;
    archivedKeys.add(key);
    const duplicateLive = rows.some(({ leadId, entry: liveEntry }) => (
      leadId === record.lead_id && (liveEntry.id ? liveEntry.id === entry.id : (
        (liveEntry.started_at || liveEntry.ended_at) === (entry.started_at || entry.ended_at)
      ))
    ));
    if (duplicateLive) continue;
    rows.push({ leadId: record.lead_id || "", entry, archivedRecord: record });
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

function prospectCell(leadId, lead, crmDeleted) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  button.type = "button";
  button.className = crmDeleted ? "dial-prospect-link dial-prospect-link--removed" : "dial-prospect-link";
  const name = lead?.name || "Unnamed prospect";
  button.textContent = name;
  if (crmDeleted) {
    button.title = "Removed from CRM";
    button.addEventListener("click", () => showToast("This prospect was removed from the CRM.", true));
  } else {
    button.title = "Open in Prospects";
    button.addEventListener("click", () => focusProspect(leadId));
  }
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

function transcriptCell(focusId, lead) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  const count = lead?.transcript?.length || 0;
  button.type = "button";
  button.className = "transcript-view-button";
  button.textContent = count ? `View · ${count}` : "No transcript";
  button.disabled = count === 0;
  button.addEventListener("click", () => {
    const current = state.leads.find((item) => item.id === focusId) || lead;
    if (current) openTranscript(current);
  });
  cell.append(button);
  return cell;
}

function statusCell(crmLead, snapshot, crmDeleted) {
  const cell = document.createElement("td");
  cell.className = "status-cell";
  if (crmDeleted) {
    cell.textContent = snapshot ? crmStatusOptionText(snapshot.status, snapshot) : "—";
    return cell;
  }
  if (!crmLead) {
    cell.textContent = "—";
    return cell;
  }
  cell.append(createCrmStatusSelect(crmLead));
  return cell;
}

function cell(text) {
  const item = document.createElement("td");
  item.textContent = text;
  return item;
}
