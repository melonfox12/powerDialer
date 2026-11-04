import { postJson } from "../../_core/api.js";
import { mergeLiveState } from "../../_core/sync-state.js";
import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { showSessionSummary } from "./summary.js";
import { tearDownVoice } from "./connect.js";
import { render } from "../../core.js";
import { selectCallerIdGroup, selectDialBusinessType, selectDialPoolStatus, selectTimezone } from "./pool.js";
import { bindDialerTimezoneMenu } from "./pool-view.js";
import { startDialing } from "./session.js";
import { bindCrmStatus } from "./crm-status.js";
import { bindDialsExport } from "./dials.js";

export function bindDialer() {
  byId("startButton").addEventListener("click", startDialing);
  bindDialsExport();
  bindCrmStatus();
  byId("stopButton").addEventListener("click", async () => {
    const button = byId("stopButton");
    button.disabled = true;
    try {
      await tearDownVoice({ intentional: true });
      const result = await postJson("/api/stop");
      mergeLiveState(result);
      render();
      showSessionSummary(result.session_summary, result.previous_session);
    }
    catch (error) { showToast(error.message, true); }
    finally {
      button.disabled = !state.running;
    }
  });
  for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
    selector.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
  for (const selector of [byId("dialerPoolStatusFilter"), byId("poolStatusFilter")]) {
    selector?.addEventListener("change", (event) => selectDialPoolStatus(event.target.value));
  }
  byId("dialerBusinessTypeFilter")?.addEventListener("change", (event) => {
    selectDialBusinessType(event.target.value);
  });
  byId("dialerCallerIdGroup")?.addEventListener("change", (event) => {
    selectCallerIdGroup(event.target.value);
  });
  bindDialerTimezoneMenu();
  const callDesk = document.querySelector(".dialer-run-panel");
  callDesk.addEventListener("click", (event) => {
    if (!event.target.closest("button, input, select, summary, a")) callDesk.focus();
  });
}
