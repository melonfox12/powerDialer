import { S, state } from "../../store/state.js";
import { byId, setText } from "../../utils/format.js";
import { renderTranscriptEntries, transcriptTimestamp } from "../../utils/transcript.js";
import { drawProspectWaveform, renderDialedProspect } from "../dialer/card.js";

export function renderCallMonitor() {
  const activity = state.activity_log || [];
  const activityList = byId("activityLog");
  setText("activityCount", `${activity.length} event${activity.length === 1 ? "" : "s"}`);
  activityList.replaceChildren(...activity.slice(-16).map((entry) => {
    const row = document.createElement("li");
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp).replace(/:\d{2}$/, "");
    const source = document.createElement("span");
    source.className = `activity-source activity-source-${entry.source || "dialer"}`;
    source.textContent = entry.source || "dialer";
    const message = document.createElement("span");
    message.className = "activity-message";
    message.textContent = entry.message || "";
    row.append(timestamp, source, message);
    return row;
  }));
  activityList.scrollTop = activityList.scrollHeight;

  const liveTranscript = state.live_transcript || {};
  const lead = state.active_lead || state.pending_outcome ||
    state.leads.find((item) => item.id === liveTranscript.lead_id) || null;
  const partials = lead && liveTranscript.lead_id === lead.id ? liveTranscript.partials || [] : [];
  const liveLines = lead && liveTranscript.lead_id === lead.id ? liveTranscript.lines || [] : [];
  const merged = new Map();
  for (const entry of [...(lead?.transcript || []), ...liveLines, ...partials]) {
    const key = entry.id || `${entry.timestamp || ""}|${entry.speaker || ""}|${entry.text || ""}`;
    merged.set(key, entry);
  }
  const entries = [...merged.values()];
  const waitingCall = (state.in_flight || []).find((call) => call.state === "listening");
  const dialingCall = (state.in_flight || []).some((call) => ["creating", "ringing"].includes(call.state));
  const monitorActivity = byId("monitorActivity");
  const answeredBy = state.pickup_answered_by || liveTranscript.answered_by || "";
  const status = state.active_lead
    ? (answeredBy === "voicemail" ? "Voicemail" : "Live")
    : waitingCall ? "Listening"
      : dialingCall ? "Dialing"
        : state.pending_outcome ? "Wrap-up"
          : state.agent_ready ? "Waiting"
            : state.running ? "Connecting" : "Idle";
  const statusState = status.toLowerCase();
  monitorActivity.dataset.state = ["dialing", "listening", "live", "voicemail"].includes(statusState) ? statusState : "idle";
  byId("enterLiveButton").hidden = !waitingCall;
  byId("enterLiveButton").disabled = S.enteringLiveLine;
  const onLine = Boolean(state.active_lead);
  byId("keepLineButton").hidden = !onLine;
  byId("keepLineButton").disabled = S.keptLineId && S.keptLineId === state.active_lead?.id;
  byId("keepLineButton").textContent = S.keptLineId === state.active_lead?.id ? "Keeping" : "Keep";
  renderDialedProspect();
  setText("monitorStatus", status);
  setText("transcriptLiveStatus", liveTranscript.lead_id === lead?.id && (liveTranscript.transcribing || onLine)
    ? (answeredBy === "voicemail" ? "Voicemail" : "Live")
    : entries.length ? "Saved" : "Waiting");
  const transcriptKey = JSON.stringify([lead?.id || null, entries]);
  if (transcriptKey !== S.lastLiveTranscriptKey) {
    S.lastLiveTranscriptKey = transcriptKey;
    renderTranscriptEntries(
      byId("liveTranscript"),
      entries,
      lead ? "Waiting for the first words…" : "Transcript appears here as the prospect and agent speak.",
      true,
    );
  }
}

export function bindCallMonitor() {
  byId("callMonitorDisclosure").addEventListener("toggle", () => {
    if (byId("callMonitorDisclosure").open) {
      renderCallMonitor();
      byId("liveTranscript").scrollTop = byId("liveTranscript").scrollHeight;
      drawProspectWaveform();
    }
  });
}
