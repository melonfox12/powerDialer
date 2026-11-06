import { S, state } from "../../_core/state.js";
import {
  byId,
  dialerById,
  dialerMirrorNodes,
  dialerWorkspacePanel,
  setDialerText,
  DEFAULT_DIAL_POOL_STATUS,
  DIAL_POOL_STATUS_LABELS,
} from "../../_core/format.js";
import { renderCallStage } from "./stage.js";
import { renderDialerControls } from "./controls.js";
import { renderOutcomeRow } from "./outcome-row.js";
import { renderCrmStatus } from "./crm-status.js";
import { renderQueueStrip } from "./queue.js";
import { renderSessionMomentum } from "./session-goal.js";
import { renderProspectNotesPanel } from "./notes-panel.js";

export function renderDialer() {
  const stage = state.stage || "idle";
  const connected = state.running && state.agent_ready;
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const activeLeadId = active?.id || null;
  if (activeLeadId && activeLeadId !== S.observedActiveLeadId) {
    for (const disclosure of dialerMirrorNodes("callMonitorDisclosure")) disclosure.open = true;
  }
  S.observedActiveLeadId = activeLeadId;
  const busy = state.running || Boolean(pending);
  const connection = byId("connectionState");
  connection.classList.toggle("busy", busy && !state.last_error);
  connection.classList.toggle("error", Boolean(state.last_error));
  connection.querySelector("span:last-child").textContent = state.last_error
    ? "Needs attention"
    : pending ? "Outcome needed" : state.paused ? "Paused" : connected ? "Dialing" : state.running ? "Connecting" : "Ready";

  const indicator = dialerWorkspacePanel()?.querySelector(".live-indicator");
  indicator.classList.remove("on", "tone-amber", "tone-success", "tone-primary", "is-pulsing");
  if (pending) indicator.classList.add("tone-amber");
  else if (active) indicator.classList.add("tone-success", "is-pulsing");
  else if (state.paused) indicator.classList.add("tone-primary");
  else if (stage === "dialing" || stage === "ringing") indicator.classList.add("tone-amber", "is-pulsing");
  else if (state.running) indicator.classList.add("tone-amber");
  setDialerText("liveLabel", pending ? "Outcome needed" : active ? "Live" : state.paused ? "Paused" : connected ? "Dialing" : state.running ? "Connecting" : "Standby");
  const poolMode = state.dial_pool_status || DEFAULT_DIAL_POOL_STATUS;
  const poolLabel = DIAL_POOL_STATUS_LABELS[poolMode] || "New";
  const queueSize = state.queue_count ?? state.pool?.length ?? 0;
  setDialerText("lineCount", `${state.session_stats?.dials || 0} of ${queueSize} ${poolLabel.toLowerCase()} dialed`);
  const lede = dialerById("dialerIssueLede");
  if (lede) {
    lede.textContent = poolMode === "contact_engaged"
      ? "Contact (engaged) pool — three lines dial at once. The first answer stays on the line."
      : "Three lines dial at once. The first answer stays on the line.";
  }
  dialerById("dialerMessage").hidden = !state.last_error;
  setDialerText("dialerMessage", state.last_error || "");
  dialerById("dialerMessage").classList.toggle("error", Boolean(state.last_error));

  const target = active || pending;
  const ringing = state.in_flight?.some((call) => call.state === "ringing");
  renderQueueStrip(active, pending, target);
  renderDialerControls(stage, active, ringing);
  renderCrmStatus();
  renderOutcomeRow(pending);
  renderSessionMomentum();
  renderCallStage(stage, target);
  renderProspectNotesPanel();
}
