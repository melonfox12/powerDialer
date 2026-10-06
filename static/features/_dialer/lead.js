import { postJson, request } from "../../_core/api.js";
import { S, state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { stopProspectWaveform } from "./card.js";
import { render } from "../../core.js";
import { openSettings } from "../settings.js";
import { connectAndCleanup, prospectLabel } from "./connect.js";

export async function dialLead(lead) {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  let cleaned = false;
  try {
    const session = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/dial`);
    const dialStatus = session.dial_status || "";
    const clientCallToken = session.client_call_token || "";
    delete session.client_call_token;
    delete session.dial_status;
    if (clientCallToken) {
      sessionStarted = true;
      const failure = await connectAndCleanup(clientCallToken, session);
      if (failure) {
        cleaned = true;
        throw failure;
      }
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
    if (!cleaned) {
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
    }
    throw error;
  } finally {
    byId("startButton").disabled = state.running;
  }
}
