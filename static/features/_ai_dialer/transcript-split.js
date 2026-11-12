import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export function renderAiListenState() {
  const button = byId("aiDialerAgent-listenInButton");
  if (!button) return;
  const onLine = Boolean(state.active_lead);
  const serverVoice = state.requires_browser_voice === false;
  const canListen = state.running && onLine && !state.pending_outcome && !serverVoice;
  button.disabled = !canListen || S.voiceConnectBusy;
  button.title = serverVoice ? "AI uses server audio — follow the live transcript." : "";
  button.dataset.state = S.voiceCall ? "listening" : canListen ? "ready" : "idle";
  button.textContent = S.voiceCall ? "Listening…" : "Listen in";
}
