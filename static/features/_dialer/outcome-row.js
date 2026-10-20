import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export function renderOutcomeRow() {
  const advancing = Boolean(state.advance_at && !state.paused);
  byId("advanceControls").hidden = !advancing;
  byId("autoAdvance").hidden = !advancing;
  if (advancing) {
    const seconds = Math.max(0, Math.ceil(Number(state.advance_at) - Date.now() / 1000));
    byId("autoAdvance").textContent = `Next prospect dialing in ${seconds}s`;
  }
}
