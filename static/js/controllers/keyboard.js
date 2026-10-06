import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export function bindKeyboard() {
  document.addEventListener("keydown", (event) => {
    const keyTarget = event.target instanceof Element ? event.target : null;
    if (keyTarget?.closest("input, textarea, select, [contenteditable=true]")) return;
    if ([...document.querySelectorAll("dialog")].some((dialog) => dialog.open)) return;
    if (!byId("loginGate").hidden) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const key = event.key.toLowerCase();
    const onActivator = Boolean(keyTarget?.closest("button, a, summary"));
    if (["1", "2", "3", "4", "5"].includes(key) && state.stage === "wrapup" && state.pending_outcome && !S.outcomeSubmitting) {
      event.preventDefault();
      byId(["outcomeBookedButton", "outcomeCallButton", "outcomeDisqualifiedButton", "outcomeNoAnswerButton", "outcomeDncButton"][Number(key) - 1]).click();
      return;
    }
    if ((event.key === " " || event.key === "Enter") && onActivator) return;
    if (event.key === " " && !event.repeat) {
      event.preventDefault();
      if (state.advance_at && !state.paused) byId("advanceNowButton").click();
      else if (state.paused) byId("pauseButton").click();
      else if (!state.running) byId("startButton").click();
    } else if (key === "h" && (state.active_lead || state.in_flight?.some((call) => call.state === "ringing"))) {
      event.preventDefault();
      byId("hangupButton").click();
    } else if (event.key === "Escape" && state.running && !state.paused) {
      event.preventDefault();
      byId("pauseButton").click();
    } else if (event.key === "?") {
      const help = document.querySelector(".shortcut-help");
      help.open = !help.open;
    }
  });
}
