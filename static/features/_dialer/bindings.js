import { postJson } from "../../_core/api.js";
import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { showSessionSummary } from "./summary.js";
import { stopProspectWaveform } from "./card.js";
import { render } from "../../core.js";
import { selectTimezone } from "./pool.js";
import { bindDialerTimezoneMenu } from "./pool-view.js";
import { startDialing } from "./session.js";
import { bindCrmStatus } from "./crm-status.js";

async function scanCrm() {
  const button = byId("scanCrmButton");
  if (button.disabled) return;
  button.disabled = true;
  button.textContent = "Scanning…";
  try {
    const result = await postJson("/api/dials/scan");
    Object.assign(state, result.state);
    render();
    const count = result.synced || 0;
    showToast(count ? `Synced ${count} prospect${count === 1 ? "" : "s"} from Total dials` : "No unsynced prospects");
  }
  catch (error) { showToast(error.message, true); }
  finally {
    button.disabled = false;
    button.textContent = "Scan CRM";
  }
}

export function bindDialer() {
  byId("startButton").addEventListener("click", startDialing);
  byId("scanCrmButton").addEventListener("click", scanCrm);
  bindCrmStatus();
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
  for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
    selector.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
  bindDialerTimezoneMenu();
  const callDesk = document.querySelector(".dialer-run-panel");
  callDesk.addEventListener("click", (event) => {
    if (!event.target.closest("button, input, select, summary, a")) callDesk.focus();
  });
}
