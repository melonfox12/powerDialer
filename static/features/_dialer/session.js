import { postJson, request } from "../../_core/api.js";
import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { stopProspectWaveform } from "./card.js";
import { render } from "../../js/views/render.js";
import { openSettings } from "../settings.js";
import { connectAndCleanup } from "./connect.js";

export async function startDialing() {
  byId("startButton").disabled = true;
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
    S.voiceDevice?.destroy();
    S.voiceDevice = null;
    S.voiceCall = null;
    stopProspectWaveform();
    Object.assign(state, await request("/api/state").catch(() => ({})));
    render();
    showToast(error.message, true);
    if (!sessionStarted) openSettings();
  } finally {
    byId("startButton").disabled = state.running;
  }
}
