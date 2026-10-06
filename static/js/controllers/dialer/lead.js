import { postJson, request } from "../../../_core/api.js";
import { S, state } from "../../../_core/state.js";
import { byId } from "../../../_core/format.js";
import { showToast } from "../../../_core/notify.js";
import { stopProspectWaveform } from "../../views/dialer/card.js";
import { render } from "../../views/render.js";
import { openSettings } from "../../../features/settings.js";
import { connectBrowserCall, prospectLabel } from "./connect.js";

export async function dialLead(lead) {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  try {
    const session = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/dial`);
    const dialStatus = session.dial_status || "";
    const clientCallToken = session.client_call_token || "";
    delete session.client_call_token;
    delete session.dial_status;
    if (clientCallToken) {
      sessionStarted = true;
      Object.assign(state, session);
      render();
      await connectBrowserCall(clientCallToken);
      Object.assign(state, await request("/api/state"));
      render();
    } else {
      Object.assign(state, session);
      render();
    }
    const name = prospectLabel(lead);
    const message = dialStatus === "already"
      ? `Already dialing ${name}`
      : dialStatus === "next"
        ? `${name} will be dialed next`
        : `Calling ${name}`;
    showToast(message);
  } catch (error) {
    if (sessionStarted) {
      await postJson("/api/stop").catch(() => {});
      S.voiceDevice?.destroy();
      S.voiceDevice = null;
      S.voiceCall = null;
      stopProspectWaveform();
    }
    Object.assign(state, await request("/api/state").catch(() => ({})));
    render();
    showToast(error.message, true);
    if (!sessionStarted && /settings/i.test(error.message || "")) openSettings();
    throw error;
  } finally {
    byId("startButton").disabled = state.running;
  }
}
