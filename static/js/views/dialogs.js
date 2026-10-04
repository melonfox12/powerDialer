import { debugEvent } from "../api/client.js";
import { startDialing } from "../controllers/dialer.js";
import { S, state } from "../store/state.js";
import { byId, setText } from "../utils/format.js";
import { downloadTranscript } from "../utils/transcript.js";

export function showSessionSummary(summary, previous) {
  if (!summary) return;
  const minutes = Math.floor((summary.duration_seconds || 0) / 60);
  const seconds = (summary.duration_seconds || 0) % 60;
  setText("sessionSummaryDuration", `Session length · ${minutes}m ${seconds}s`);
  const values = [
    ["Dials", summary.dials],
    ["Connects", summary.connects],
    ["Conversations", summary.conversations],
    ["Meetings booked", summary.meetings_booked],
    ["Best streak", summary.best_streak],
  ];
  byId("sessionSummaryStats").replaceChildren(...values.map(([label, value]) => {
    const item = document.createElement("div");
    const title = document.createElement("span");
    title.textContent = label;
    const count = document.createElement("strong");
    count.textContent = String(value || 0);
    item.append(title, count);
    return item;
  }));
  const comparison = byId("sessionComparison");
  const delta = previous ? (summary.conversations || 0) - (previous.conversations || 0) : 0;
  comparison.hidden = !previous;
  comparison.textContent = previous
    ? `${delta >= 0 ? "+" : ""}${delta} conversations vs. previous session`
    : "";
  byId("sessionSummaryDialog").showModal();
}

export function showToast(message, isError = false) {
  if (isError) debugEvent("error", "toast", message);
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(S.toastTimer);
  S.toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

export function bindDialogs() {
  byId("closeTranscript").addEventListener("click", () => byId("transcriptDialog").close());
  byId("downloadTranscriptButton").addEventListener("click", () => {
    const lead = state.leads.find((item) => item.id === byId("downloadTranscriptButton").dataset.leadId);
    if (lead) downloadTranscript(lead);
  });
  byId("transcriptDialog").addEventListener("click", (event) => {
    if (event.target === byId("transcriptDialog")) byId("transcriptDialog").close();
  });
  byId("closeSessionSummary").addEventListener("click", () => byId("sessionSummaryDialog").close());
  byId("startNewSession").addEventListener("click", () => {
    byId("sessionSummaryDialog").close();
    startDialing();
  });
}
