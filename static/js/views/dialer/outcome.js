import { S, state } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";

export function renderOutcomeRow(pending) {
  const outcomeLead = pending;
  const outcomeDisabled = !outcomeLead || S.outcomeSubmitting;
  byId("outcomeRow").hidden = !outcomeLead;
  byId("outcomeCallButton").disabled = outcomeDisabled;
  byId("outcomeBookedButton").disabled = outcomeDisabled;
  byId("outcomeDisqualifiedButton").disabled = outcomeDisabled;
  for (const id of ["outcomeNoAnswerButton", "outcomeDncButton"]) byId(id).disabled = outcomeDisabled;
  const callbackPicker = byId("callbackPicker");
  callbackPicker.hidden = !state.pending_outcome || !callbackPicker.dataset.open;
  const advancing = Boolean(state.advance_at && !state.paused);
  byId("advanceControls").hidden = !advancing;
  byId("autoAdvance").hidden = !advancing;
  byId("advanceNowButton").hidden = !advancing;
  if (advancing) {
    const seconds = Math.max(0, Math.ceil(Number(state.advance_at) - Date.now() / 1000));
    byId("autoAdvance").textContent = `Next prospect dialing in ${seconds}s · Space to skip`;
  }
  if (!state.pending_outcome) callbackPicker.dataset.open = "";
}
