import { state } from "../../_core/state.js";
import { STATUS_LABELS, byId, setText } from "../../_core/format.js";
import { openTranscript } from "../../_core/transcript.js";

export function renderDials() {
  const rows = dialRows(state.leads);
  setText("dialsTabCount", String(rows.length));
  setText("dialsTableSummary", `${rows.length} call${rows.length === 1 ? "" : "s"}`);
  const body = byId("dialsTableBody");
  body.replaceChildren(...rows.map(({ lead, entry }) => {
    const row = document.createElement("tr");
    row.append(cell(dialWhen(entry.ended_at || entry.started_at)));
    row.append(cell(lead.name || "Unnamed prospect"));
    row.append(cell(lead.business || "—"));
    row.append(cell(reviewText(lead)));
    row.append(transcriptCell(lead));
    row.append(cell(STATUS_LABELS[lead.status] || "New"));
    return row;
  }));
  byId("dialsTable").hidden = rows.length === 0;
  byId("dialsTableEmpty").classList.toggle("visible", rows.length === 0);
}

function dialRows(leads) {
  const rows = [];
  for (const lead of leads || []) {
    const log = lead.call_log || [];
    for (const entry of log) rows.push({ lead, entry });
    if (!log.length && lead.transcript?.length) {
      const stamps = lead.transcript.map((line) => line.timestamp).filter(Boolean).sort();
      rows.push({
        lead,
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
  const count = lead.review_count;
  if (count === 0 || count) return String(count);
  return "—";
}

function transcriptCell(lead) {
  const cell = document.createElement("td");
  const button = document.createElement("button");
  const count = lead.transcript?.length || 0;
  button.type = "button";
  button.className = "transcript-view-button";
  button.textContent = count ? `View · ${count}` : "No transcript";
  button.disabled = count === 0;
  button.addEventListener("click", () => openTranscript(lead));
  cell.append(button);
  return cell;
}

function cell(text) {
  const item = document.createElement("td");
  item.textContent = text;
  return item;
}
