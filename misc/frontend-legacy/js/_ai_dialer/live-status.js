import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
function liveLabelText() {
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const connected = state.running && state.agent_ready;
  if (pending) return "Outcome needed";
  if (active) return "Live";
  if (state.paused) return "Paused";
  if (connected) return "Dialing";
  if (state.running) return "Connecting";
  return "Standby";
}

export function renderAiLiveStatus() {
  const menu = document.querySelector("#aiDialerAgent-detailView .ai-dialer-menu");
  const indicator = menu?.querySelector(".live-indicator");
  const label = byId("aiDialerAgent-liveLabel");
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const stage = state.stage || "idle";
  if (label) label.textContent = liveLabelText();
  if (!indicator) return;
  indicator.classList.remove("on", "tone-amber", "tone-success", "tone-primary", "is-pulsing");
  if (pending) indicator.classList.add("tone-amber");
  else if (active) indicator.classList.add("tone-success", "is-pulsing");
  else if (state.paused) indicator.classList.add("tone-primary");
  else if (stage === "dialing" || stage === "ringing") indicator.classList.add("tone-amber", "is-pulsing");
  else if (state.running) indicator.classList.add("tone-amber");

  const message = byId("aiDialerAgent-dialerMessage");
  if (message) {
    const bridgeWarning =
      state.running && state.ai_voice_configured === false
        ? "AI voice bridge is not configured (WSS URL + secret in Settings)."
        : "";
    const text = state.last_error || bridgeWarning;
    message.hidden = !text;
    message.textContent = text;
    message.classList.toggle("error", Boolean(state.last_error || bridgeWarning));
  }

  const transcriptPill = byId("aiDialerAgent-transcriptLiveStatus");
  if (!transcriptPill) return;
  const liveTranscript = state.live_transcript || {};
  const onLine = Boolean(state.active_lead);
  const answeredBy = state.pickup_answered_by || liveTranscript.answered_by || "";
  const aiStream = Boolean(state.ai_voice_stream_active);
  transcriptPill.textContent = onLine
    ? (answeredBy === "voicemail" ? "Voicemail" : aiStream ? "AI on the line" : "On the line")
    : state.running
      ? "Waiting for a pickup"
      : "Standby";

  const start = byId("aiDialerAgent-startButton");
  const stop = byId("aiDialerAgent-stopButton");
  if (stop) {
    stop.hidden = stage === "idle" && !state.running;
    stop.disabled = !state.running || S.voiceConnectBusy;
  }
  if (start) start.hidden = false;
}
