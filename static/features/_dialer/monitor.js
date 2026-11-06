import { S, state } from "../../_core/state.js";
import { dialerMirrorNodes, setDialerText } from "../../_core/format.js";
import { renderTranscriptEntries, transcriptTimestamp } from "../../_core/transcript.js";
import { drawProspectWaveform, renderDialedProspect } from "./card.js";

export function renderCallMonitor() {
  const activity = state.activity_log || [];
  setDialerText("activityCount", `${activity.length} event${activity.length === 1 ? "" : "s"}`);
  const activityItems = [];
  if (!activity.length) {
    const emptyRow = document.createElement("li");
    emptyRow.className = "monitor-empty";
    emptyRow.textContent = "Waiting for dialer activity.";
    activityItems.push(emptyRow);
  } else {
    for (const entry of activity.slice(-16)) {
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
      activityItems.push(row);
    }
  }
  for (const activityList of dialerMirrorNodes("activityLog")) {
    activityList.replaceChildren(...activityItems.map((node) => node.cloneNode(true)));
    activityList.scrollTop = activityList.scrollHeight;
  }

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
  const dialingCall = (state.in_flight || []).some((call) => ["creating", "ringing"].includes(call.state));
  const answeredBy = state.pickup_answered_by || liveTranscript.answered_by || "";
  const status = state.active_lead
    ? (answeredBy === "voicemail" ? "Voicemail" : "Live")
    : dialingCall ? "Dialing"
      : state.pending_outcome ? "Wrap-up"
        : state.agent_ready ? "Waiting"
          : state.running ? "Connecting" : "Idle";
  const statusState = status.toLowerCase();
  for (const monitorActivity of dialerMirrorNodes("monitorActivity")) {
    monitorActivity.dataset.state = ["dialing", "live", "voicemail"].includes(statusState) ? statusState : "idle";
  }
  const onLine = Boolean(state.active_lead);
  renderDialedProspect();
  setDialerText("monitorStatus", status);
  setDialerText("transcriptLiveStatus", liveTranscript.lead_id === lead?.id && (liveTranscript.transcribing || onLine)
    ? (answeredBy === "voicemail" ? "Voicemail" : "Live")
    : entries.length ? "Saved" : "Waiting");
  const transcriptKey = JSON.stringify([lead?.id || null, entries]);
  if (transcriptKey !== S.lastLiveTranscriptKey) {
    S.lastLiveTranscriptKey = transcriptKey;
    for (const liveNode of dialerMirrorNodes("liveTranscript")) {
      renderTranscriptEntries(
        liveNode,
        entries,
        lead ? "Waiting for the first words…" : "Transcript appears here as the prospect and agent speak.",
        true,
      );
    }
  }
}

export function bindCallMonitor() {
  for (const disclosure of dialerMirrorNodes("callMonitorDisclosure")) {
    disclosure.addEventListener("toggle", () => {
      if (!disclosure.open) return;
      renderCallMonitor();
      for (const live of dialerMirrorNodes("liveTranscript")) {
        live.scrollTop = live.scrollHeight;
      }
      drawProspectWaveform();
    });
  }
}
