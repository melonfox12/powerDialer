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

let openTranscriptImpl = () => {};
let downloadTranscriptImpl = () => {};

export function registerTranscriptActions(open, download) {
  openTranscriptImpl = open;
  downloadTranscriptImpl = download;
}

export function openTranscript(lead) {
  openTranscriptImpl(lead);
}

export function downloadTranscript(lead) {
  downloadTranscriptImpl(lead);
}
