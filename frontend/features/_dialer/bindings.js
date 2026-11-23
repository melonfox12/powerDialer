import { postJson } from "../../_core/api.js";
import { mergeLiveState } from "../../_core/sync-state.js";
import { S, state } from "../../_core/state.js";
import { dialerEl, dialerEls } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { showSessionSummary } from "./summary.js";
import { tearDownVoice } from "./connect.js";
import { render } from "../../core.js";
import { selectCallerIdGroup, selectDialBusinessType, selectDialPoolStatus, selectTimezone } from "./pool.js";
import { bindDialerTimezoneMenu } from "./pool-view.js";
import { startDialing } from "./session.js";
import { bindCrmStatus } from "./crm-status.js";
import { bindDialsExport } from "./dials.js";
import { bindNotesSidebar } from "./notes-sidebar.js";

export function bindDialer() {
  bindNotesSidebar();
  dialerEl("startButton")?.addEventListener("click", startDialing);
  bindDialsExport();
  bindCrmStatus();
  dialerEl("stopButton")?.addEventListener("click", async () => {
    const stopButton = dialerEl("stopButton");
    if (!stopButton) return;
    stopButton.disabled = true;
    try {
      await tearDownVoice({ intentional: true });
      const result = await postJson("/api/stop");
      mergeLiveState(result);
      render();
      showSessionSummary(result.session_summary, result.previous_session);
    }
    catch (error) { showToast(error.message, true); }
    finally {
      const node = dialerEl("stopButton");
      if (node) node.disabled = !state.running;
    }
  });
  const timezoneSelectors = [dialerEl("dialerTimezoneFilter"), document.getElementById("poolTimezoneFilter")].filter(Boolean);
  for (const selector of timezoneSelectors) {
    selector?.addEventListener("change", (event) => selectTimezone(event.target.value));
  }
  const poolStatusSelectors = [dialerEl("dialerPoolStatusFilter"), document.getElementById("poolStatusFilter")].filter(Boolean);
  for (const selector of poolStatusSelectors) {
    selector?.addEventListener("change", (event) => selectDialPoolStatus(event.target.value));
  }
  dialerEl("dialerBusinessTypeFilter")?.addEventListener("change", (event) => selectDialBusinessType(event.target.value));
  dialerEl("dialerCallerIdGroup")?.addEventListener("change", (event) => selectCallerIdGroup(event.target.value));
  bindDialerTimezoneMenu();
  for (const panel of document.querySelectorAll(".dialer-run-panel")) {
    panel.addEventListener("click", (event) => {
      if (!event.target.closest("button, input, select, summary, a")) panel.focus();
    });
  }
}
