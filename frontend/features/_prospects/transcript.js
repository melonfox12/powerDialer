import { byId } from "../../_core/format.js";
import { state } from "../../_core/state.js";
import { renderTranscriptEntries } from "../../_core/transcript.js";
import { bindSessionSummary } from "../dialer.js";

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

export function bindDialogs() {
  byId("closeTranscript").addEventListener("click", () => byId("transcriptDialog").close());
  byId("transcriptDialog").addEventListener("click", (event) => {
    if (event.target === byId("transcriptDialog")) byId("transcriptDialog").close();
  });
  byId("downloadTranscriptButton").addEventListener("click", () => {
    const lead = state.leads.find((item) => item.id === byId("downloadTranscriptButton").dataset.leadId);
    if (lead) downloadTranscript(lead);
  });
  bindSessionSummary();
}
