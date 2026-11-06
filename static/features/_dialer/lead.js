import { postJson } from "../../_core/api.js";
import { loadAppState, mergeLiveState } from "../../_core/sync-state.js";
import { S, state } from "../../_core/state.js";
import { dialerMirrorNodes } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../../core.js";
import { openSettings } from "../settings.js";
import { connectAndCleanup, prospectLabel, tearDownVoice } from "./connect.js";

export async function dialLead(lead) {
  for (const button of dialerMirrorNodes("startButton")) button.disabled = true;
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
      mergeLiveState(session);
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
        await tearDownVoice({ intentional: true });
      }
      await loadAppState().catch(() => {});
      render();
      showToast(error.message, true);
      if (!sessionStarted && /settings/i.test(error.message || "")) openSettings();
    }
    throw error;
  } finally {
    for (const button of dialerMirrorNodes("startButton")) button.disabled = state.running;
  }
}
