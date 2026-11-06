import { postJson } from "../../_core/api.js";
import { loadAppState } from "../../_core/sync-state.js";
import { S, state } from "../../_core/state.js";
import { dialerMirrorNodes } from "../../_core/format.js";
import { errorText, showToast } from "../../_core/notify.js";
import { render } from "../../core.js";
import { openSettings } from "../settings.js";
import { connectAndCleanup, tearDownVoice } from "./connect.js";

export async function startDialing() {
  for (const button of dialerMirrorNodes("startButton")) button.disabled = true;
  S.voiceConnectBusy = true;
  let sessionStarted = false;
  try {
    const session = await postJson("/api/start");
    sessionStarted = true;
    const { client_call_token: clientCallToken, ...sessionState } = session;
    if (!clientCallToken) throw new Error("The browser call session could not be created.");
    const failure = await connectAndCleanup(clientCallToken, sessionState);
    if (failure) return;
  } catch (error) {
    if (sessionStarted) await postJson("/api/stop").catch(() => {});
    await tearDownVoice({ intentional: true });
    await loadAppState().catch(() => {});
    render();
    showToast(errorText(error, "Could not start dialing."), true);
    if (!sessionStarted) openSettings();
  } finally {
    if (!state.running) S.voiceConnectBusy = false;
    for (const button of dialerMirrorNodes("startButton")) button.disabled = state.running;
  }
}
