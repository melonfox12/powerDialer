import { arcadeSensory, celebrateBooked, playCue } from "./arcade.js";
import { registerCallerPool, registerRenderer } from "../core.js";
import { drawProspectWaveform } from "./_dialer/card.js";
import { stageEffects } from "./_dialer/effects.js";
import { dialLead } from "./_dialer/lead.js";
import { bindCallMonitor } from "./_dialer/monitor.js";
import { renderCallerPool } from "./_dialer/pool-view.js";
import { renderDialer } from "./_dialer/render-dialer.js";
import { startDialing } from "./_dialer/session.js";
import { bindSessionGoal } from "./_dialer/session-goal.js";
import { setStartNewSession } from "./_dialer/summary.js";
import { bindVoice } from "./_dialer/_voice/connect.js";

stageEffects.playCue = playCue;
stageEffects.match = (lead) => arcadeSensory.match(lead);
stageEffects.reset = (quiet) => arcadeSensory.reset(quiet);
stageEffects.stop = () => arcadeSensory.stop();
stageEffects.startSpin = (key) => arcadeSensory.startSpin(key);
stageEffects.goalReached = () => {
  if (arcadeSensory.preferences.enabled) arcadeSensory.burstParticles();
};
stageEffects.booked = (lead) => {
  celebrateBooked();
  arcadeSensory.match(lead);
};

setStartNewSession(startDialing);
registerCallerPool(renderCallerPool);
registerRenderer(() => {
  renderCallerPool();
  renderDialer();
});

export { bindDialer } from "./_dialer/bindings.js";
export { bindKeyboard } from "./_dialer/keyboard.js";
export { bindOutcomes } from "./_dialer/outcomes.js";
export { refreshState, startPolling } from "./_dialer/poller.js";
export { bindSessionSummary, showSessionSummary } from "./_dialer/summary.js";
export { bindCallMonitor, bindSessionGoal, bindVoice, dialLead, drawProspectWaveform, startDialing };
