import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { formatPhoneNumber } from "../../_core/phone.js";
import { renderCallMonitor } from "./monitor.js";

export function renderDialerControls(stage) {
  byId("startButton").disabled = state.running;
  byId("startButton").hidden = stage !== "idle";
  byId("stopButton").disabled = !state.running;
  byId("stopButton").hidden = stage === "idle";
  document.querySelector(".dialer-controls").dataset.controls = stage;
  const caller = state.current_caller_id || "";
  const callerIds = state.caller_ids || [];
  const callerIndex = caller ? callerIds.indexOf(caller) : -1;
  const callerLabel = caller
    ? `${formatPhoneNumber(caller)}${callerIds.length > 1 && callerIndex >= 0 ? ` · ${callerIndex + 1} of ${callerIds.length}` : ""}`
    : "";
  byId("callerIdLine").hidden = !callerLabel;
  byId("callerIdLine").querySelector("span").textContent = callerLabel;
  renderCallMonitor();
}
