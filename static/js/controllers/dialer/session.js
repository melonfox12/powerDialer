import { postJson, request } from "../../../_core/api.js";
import { S, state } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";
import { showToast } from "../../../_core/notify.js";
import { stopProspectWaveform } from "../../views/dialer/card.js";
import { render } from "../../views/render.js";
import { openSettings } from "../../../features/settings.js";
import { connectBrowserCall } from "./connect.js";

export async function startDialing() {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  try {
    const session = await postJson("/api/start");
    sessionStarted = true;
    const { client_call_token: clientCallToken, ...sessionState } = session;
    if (!clientCallToken) throw new Error("The browser call session could not be created.");
    Object.assign(state, sessionState);
    render();
    await connectBrowserCall(clientCallToken);
    Object.assign(state, await request("/api/state"));
    render();
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
