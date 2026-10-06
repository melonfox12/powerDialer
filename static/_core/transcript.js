import { byId } from "./format.js";

export function transcriptTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function renderTranscriptEntries(container, entries, emptyMessage, followLatest = false) {
  const previousScrollTop = container.scrollTop;
  const shouldFollowLatest = followLatest &&
    container.scrollHeight - container.scrollTop - container.clientHeight <= 28;
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "transcript-empty";
    empty.textContent = emptyMessage;
    container.replaceChildren(empty);
    if (followLatest) container.scrollTop = shouldFollowLatest ? container.scrollHeight : previousScrollTop;
    return;
  }
  const ordered = [...entries].sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  container.replaceChildren(...ordered.map((entry) => {
    const row = document.createElement("article");
    row.className = `transcript-entry transcript-entry-${String(entry.speaker || "unknown").toLowerCase()}`;
    const meta = document.createElement("div");
    meta.className = "transcript-entry-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = entry.speaker || "Speaker";
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp);
    const text = document.createElement("p");
    text.textContent = entry.text || "";
    meta.append(speaker, timestamp);
    row.append(meta, text);
    return row;
  }));
  if (followLatest) container.scrollTop = shouldFollowLatest ? container.scrollHeight : previousScrollTop;
}

export function openTranscript(lead) {
  const entries = lead.transcript || [];
  byId("transcriptDialogTitle").textContent = `${lead.name || lead.business || lead.phone} · Transcript`;
  byId("transcriptDialogMeta").textContent = `${lead.phone || ""} · ${entries.length} utterance${entries.length === 1 ? "" : "s"}`;
  renderTranscriptEntries(byId("transcriptDialogBody"), entries, "No transcript has been captured for this call.");
  byId("downloadTranscriptButton").dataset.leadId = lead.id;
  byId("transcriptDialog").showModal();
}

export function downloadTranscript(lead) {
  const entries = lead.transcript || [];
  const content = entries
    .map((entry) => `[${entry.timestamp || "Time unavailable"}] ${entry.speaker || "Speaker"}: ${entry.text || ""}`)
    .join("\r\n");
  const blobUrl = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  const filenameBase = (lead.business || lead.name || lead.phone || "prospect-transcript")
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .trim()
    .replace(/\s+/g, "-")
    .slice(0, 80) || "prospect-transcript";
  anchor.href = blobUrl;
  anchor.download = `${filenameBase}-transcript.txt`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
}
