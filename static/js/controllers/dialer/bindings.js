import { postJson } from "../../../_core/api.js";
import { S, state } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";
import { showToast } from "../../../_core/notify.js";
import { renderCallMonitor } from "../../views/monitor/index.js";
import { showSessionSummary } from "../../views/dialogs/index.js";
import { stopProspectWaveform } from "../../views/dialer/card.js";
import { render } from "../../views/render.js";
import { selectTimezone } from "../pool.js";
import { startDialing } from "./session.js";

export function bindDialer() {
  byId("startButton").addEventListener("click", startDialing);
  byId("pauseButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/pause")); render(); }
    catch (error) { showToast(error.message, true); }
  });
  byId("stopButton").addEventListener("click", async () => {
    try {
      const result = await postJson("/api/stop");
      Object.assign(state, result);
      S.voiceDevice?.destroy();
      S.voiceDevice = null;
      S.voiceCall = null;
      stopProspectWaveform();
      render();
      showSessionSummary(result.session_summary, result.previous_session);
    }
    catch (error) { showToast(error.message, true); }
  });
  byId("hangupButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/hangup")); render(); }
    catch (error) { showToast(error.message, true); }
  });
  byId("keepLineButton").addEventListener("click", () => {
    if (!state.active_lead) return;
    S.keptLineId = state.active_lead.id;
    showToast("Staying on the line");
    renderCallMonitor();
  });
  byId("skipVoicemailButton").addEventListener("click", async () => {
    try {
      Object.assign(state, await postJson("/api/skip"));
      showToast("Skipped. Choose an outcome.");
      render();
    } catch (error) {
      showToast(error.message, true);
    }
  });
  for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
    selector.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
  const callDesk = document.querySelector(".dialer-run-panel");
  callDesk.addEventListener("click", (event) => {
    if (!event.target.closest("button, input, select, summary, a")) callDesk.focus();
  });
  byId("advanceNowButton").addEventListener("click", async () => {
    try { Object.assign(state, await postJson("/api/advance")); render(); }
    catch (error) { showToast(error.message, true); }
  });
}
