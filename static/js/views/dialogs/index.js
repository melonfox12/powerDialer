import { state } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";
import { downloadTranscript } from "../../../_core/transcript.js";
import { bindSessionSummary } from "../../../features/dialer.js";

export function bindDialogs() {
  byId("closeTranscript").addEventListener("click", () => byId("transcriptDialog").close());
  byId("downloadTranscriptButton").addEventListener("click", () => {
    const lead = state.leads.find((item) => item.id === byId("downloadTranscriptButton").dataset.leadId);
    if (lead) downloadTranscript(lead);
  });
  byId("transcriptDialog").addEventListener("click", (event) => {
    if (event.target === byId("transcriptDialog")) byId("transcriptDialog").close();
  });
  bindSessionSummary();
}
