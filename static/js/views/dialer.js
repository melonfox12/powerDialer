import { S, state } from "../store/state.js";
import { byId, setText } from "../utils/format.js";
import { renderCallStage } from "./call-stage/index.js";
import { renderDialerControls } from "./dialer-controls.js";
import { renderOutcomeRow } from "./outcome-row.js";
import { renderQueueStrip } from "./queue-strip.js";
import { renderSessionMomentum } from "./session-goal.js";

export function renderDialer() {
  const stage = state.stage || "idle";
  const connected = state.running && state.agent_ready;
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const activeLeadId = active?.id || null;
  if (activeLeadId && activeLeadId !== S.observedActiveLeadId) byId("callMonitorDisclosure").open = true;
  S.observedActiveLeadId = activeLeadId;
  const busy = state.running || Boolean(pending);
  const connection = byId("connectionState");
  connection.classList.toggle("busy", busy && !state.last_error);
  connection.classList.toggle("error", Boolean(state.last_error));
  connection.querySelector("span:last-child").textContent = state.last_error
    ? "Needs attention"
    : pending ? "Outcome needed" : state.paused ? "Paused" : connected ? "Dialing" : state.running ? "Connecting" : "Ready";

  const indicator = document.querySelector(".live-indicator");
  indicator.classList.remove("on", "tone-amber", "tone-success", "tone-primary", "is-pulsing");
  if (pending) indicator.classList.add("tone-amber");
  else if (active) indicator.classList.add("tone-success", "is-pulsing");
  else if (state.paused) indicator.classList.add("tone-primary");
  else if (stage === "dialing" || stage === "ringing") indicator.classList.add("tone-amber", "is-pulsing");
  else if (state.running) indicator.classList.add("tone-amber");
  setText("liveLabel", pending ? "OUTCOME REQUIRED" : active ? "LIVE CALL" : state.paused ? "DIALER PAUSED" : connected ? "DIALING" : state.running ? "CONNECTING" : "DIALER STANDBY");
  setText("lineCount", `${state.session_stats?.dials || 0} of ${state.queue_count ?? state.pool?.length ?? 0} dialed`);
  byId("dialerMessage").hidden = !state.last_error;
  setText("dialerMessage", state.last_error || "");
  byId("dialerMessage").classList.toggle("error", Boolean(state.last_error));

  const target = active || pending || (state.in_flight?.find((call) => call.state === "connecting")?.lead);
  const ringing = state.in_flight?.some((call) => call.state === "ringing");
  renderQueueStrip(active, pending, target);
  renderDialerControls(stage, active, ringing);
  renderOutcomeRow(pending);
  renderSessionMomentum();
  renderCallStage(stage, target);
}
