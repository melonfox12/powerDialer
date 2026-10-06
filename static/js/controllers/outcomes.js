import { postJson } from "../../_core/api.js";
import { celebrateBooked } from "../features/arcade/fx/audio.js";
import { arcadeSensory } from "../features/arcade/controller/index.js";
import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { localDateTimeToUtc, nextBusinessCallback, timezoneFor } from "../../_core/time.js";
import { renderDialer } from "../views/dialer/index.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../views/render.js";

export async function submitOutcome(disposition, scheduledUntil = null) {
  const lead = state.pending_outcome;
  if (!lead || S.outcomeSubmitting) return;
  S.outcomeSubmitting = true;
  render();
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, {
      disposition,
      scheduled_until: scheduledUntil,
    });
    Object.assign(state, result.state);
    byId("callbackPicker").dataset.open = "";
    if (disposition === "booked") {
      celebrateBooked();
      arcadeSensory.match(lead);
    }
    const lines = result.lead?.transcript?.length || 0;
    showToast(`${lead.name || lead.phone}: ${disposition.replaceAll("_", " ")} · status updated${lines ? ` · ${lines} transcript line${lines === 1 ? "" : "s"} saved` : ""}`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    S.outcomeSubmitting = false;
    render();
  }
}

export function bindOutcomes() {
  byId("outcomeRow").addEventListener("click", (event) => {
    const button = event.target.closest(".outcome-btn");
    if (!button || button.disabled) return;
    button.classList.remove("outcome-pressed", "outcome-pressed-booked");
    button.classList.add(button.id === "outcomeBookedButton" ? "outcome-pressed-booked" : "outcome-pressed");
    setTimeout(() => button.classList.remove("outcome-pressed", "outcome-pressed-booked"), 150);
  });
  byId("callbackAt").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    byId("saveCallbackButton").click();
  });
  byId("outcomeCallButton").addEventListener("click", () => {
    const picker = byId("callbackPicker");
    if (picker.dataset.open) {
      byId("callbackAt").focus();
      return;
    }
    if (state.pending_outcome) byId("callbackAt").value = nextBusinessCallback(state.pending_outcome);
    byId("callbackPicker").querySelector("label").textContent = state.pending_outcome?.timezone && state.pending_outcome.timezone !== "Unknown"
      ? `Call again in ${state.pending_outcome.timezone} local time`
      : "Timezone unavailable; use your local time";
    picker.dataset.open = "true";
    renderDialer();
    byId("callbackAt").focus();
  });
  byId("saveCallbackButton").addEventListener("click", () => {
    try {
      const lead = state.pending_outcome;
      const timeZone = timezoneFor(lead?.timezone);
      submitOutcome("callback", localDateTimeToUtc(byId("callbackAt").value, timeZone));
    } catch (error) {
      showToast(error.message, true);
    }
  });
  byId("outcomeBookedButton").addEventListener("click", () => submitOutcome("booked"));
  byId("outcomeDisqualifiedButton").addEventListener("click", () => submitOutcome("not_interested"));
  byId("outcomeNoAnswerButton").addEventListener("click", () => submitOutcome("no_answer"));
  byId("outcomeDncButton").addEventListener("click", () => submitOutcome("do_not_call"));
}
