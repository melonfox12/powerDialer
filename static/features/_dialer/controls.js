import { S, state } from "../../_core/state.js";
import { dialerMirrorNodes } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { renderCallMonitor } from "./monitor.js";

export function renderDialerControls(stage) {
  for (const start of dialerMirrorNodes("startButton")) {
    start.disabled = state.running;
    start.hidden = stage !== "idle";
  }
  for (const stop of dialerMirrorNodes("stopButton")) {
    stop.disabled = !state.running || S.voiceConnectBusy;
    stop.hidden = stage === "idle";
  }
  for (const panel of [document.getElementById("dialerTabPanel"), document.getElementById("aiDialerAgentTabPanel")].filter(Boolean)) {
    panel.querySelector(".dialer-controls")?.setAttribute("data-controls", stage);
  }
  const caller = state.current_caller_id || "";
  const callerIds = state.caller_ids || [];
  const callerIndex = caller ? callerIds.indexOf(caller) : -1;
  const callerLabel = caller
    ? `${formatPhoneNumber(caller)}${callerIds.length > 1 && callerIndex >= 0 ? ` · ${callerIndex + 1} of ${callerIds.length}` : ""}`
    : "";
  for (const line of dialerMirrorNodes("callerIdLine")) {
    line.hidden = !callerLabel;
    line.querySelector("span").textContent = callerLabel;
  }
  renderCallMonitor();
}
