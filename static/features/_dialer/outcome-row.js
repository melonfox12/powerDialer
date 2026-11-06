import { state } from "../../_core/state.js";
import { dialerMirrorNodes } from "../../_core/format.js";

export function renderOutcomeRow() {
  const advancing = Boolean(state.advance_at && !state.paused);
  for (const row of dialerMirrorNodes("advanceControls")) row.hidden = !advancing;
  for (const auto of dialerMirrorNodes("autoAdvance")) {
    auto.hidden = !advancing;
    if (advancing) {
      const seconds = Math.max(0, Math.ceil(Number(state.advance_at) - Date.now() / 1000));
      auto.textContent = `Next prospect dialing in ${seconds}s`;
    }
  }
}
