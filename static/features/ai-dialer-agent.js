import { registerRenderer } from "../core.js";
import { S, state } from "../_core/state.js";
import { byId } from "../_core/format.js";
import { showToast } from "../_core/notify.js";
import { errorText } from "../_core/notify.js";
import { mergeLiveState, loadAppState } from "../_core/sync-state.js";
import { connectBrowserCall, connectAndCleanup } from "./_dialer/connect.js";
import { takeLatestVoiceError } from "./_dialer/_voice/connect.js";
import { drawProspectWaveform } from "./_dialer/card.js";
import { renderAiActivityLog } from "./_ai_dialer/activity-log.js";
import { renderAiLiveStatus } from "./_ai_dialer/live-status.js";
import {
  renderAiAgentDetailStats,
  renderAiDialerFleet,
  syncAiDialerViews,
} from "./_ai_dialer/fleet.js";
import { renderTodayDialTable } from "./_ai_dialer/today-table.js";
import { renderChatTranscript } from "./_ai_dialer/chat-transcript.js";
import { renderAgentQueueList } from "./_ai_dialer/queue-panel.js";
import { renderAgentPowerSlots } from "./_ai_dialer/agent-slots.js";
import { renderAiListenState } from "./_ai_dialer/transcript-split.js";
import { primaryAgent } from "./_ai_dialer/agents.js";
import { postJson } from "../_core/api.js";
import { render } from "../core.js";
import { tearDownVoice } from "./_dialer/connect.js";

function renderAiDialerWorkspace() {
  if (S.dashboardTab !== "aiDialerAgent") return;
  syncAiDialerViews();
  renderAiDialerFleet();
  const agentId = S.aiDialerSelectedAgentId;
  if (!agentId) return;
  renderAiAgentDetailStats(agentId);
  renderAiLiveStatus();
  renderAiActivityLog();
  drawProspectWaveform();
  renderChatTranscript();
  renderAiListenState();
  renderAgentQueueList(agentId);
  renderAgentPowerSlots();
  renderTodayDialTable(agentId);
  const agent = primaryAgent();
  const slotNote = byId("aiDialerAgent-slotNotice");
  if (slotNote) {
    slotNote.hidden = agentId === agent.id;
  }
}

async function listenInOnCall() {
  if (S.voiceCall || S.voiceConnectBusy) return;
  const agent = primaryAgent();
  if (S.aiDialerSelectedAgentId !== agent.id) {
    showToast("Only the live-line agent can be monitored right now.", true);
    return;
  }
  if (!state.running || !state.active_lead) {
    showToast("There is no live call to monitor.", true);
    return;
  }
  S.voiceConnectBusy = true;
  try {
    const payload = await postJson("/api/voice/rejoin");
    const token = payload.client_call_token;
    if (!token) throw new Error("Voice monitor token missing.");
    mergeLiveState(payload);
    await connectBrowserCall(token);
    await loadAppState().catch(() => {});
    render();
    showToast("Monitoring live audio.");
  } catch (error) {
    const message = errorText(error, "") || errorText(takeLatestVoiceError(), "") || "Could not join the live call.";
    showToast(message, true);
  } finally {
    S.voiceConnectBusy = false;
    renderAiListenState();
  }
}

async function startAgentSeat(agentId) {
  const agent = primaryAgent();
  if (agentId !== agent.id) {
    showToast("Only the live-line seat can start dialing right now.", true);
    return;
  }
  for (const button of document.querySelectorAll("#aiDialerAgent-startButton")) button.disabled = true;
  try {
    const view = await postJson("/api/ai-agents/start", { agent_id: agentId });
    mergeLiveState(view);
    const token = view.client_call_token;
    if (token) {
      await connectAndCleanup(token, view);
    } else {
      await loadAppState();
      render();
    }
  } catch (error) {
    showToast(errorText(error, "Could not start agent."), true);
    for (const button of document.querySelectorAll("#aiDialerAgent-startButton")) button.disabled = state.running;
  }
}

async function stopAgentSeat(agentId) {
  try {
    await tearDownVoice({ intentional: true });
    const view = await postJson("/api/ai-agents/stop", { agent_id: agentId });
    mergeLiveState(view);
    render();
  } catch (error) {
    showToast(errorText(error, "Could not stop agent."), true);
  }
}

export function bindAiDialer() {
  const back = byId("aiDialerAgent-backToFleet");
  back?.addEventListener("click", () => {
    S.aiDialerSelectedAgentId = null;
    syncAiDialerViews();
    render();
  });
  byId("aiDialerAgent-listenInButton")?.addEventListener("click", () => {
    listenInOnCall().catch(() => {});
  });
  byId("aiDialerAgent-startButton")?.addEventListener("click", () => {
    const agentId = S.aiDialerSelectedAgentId || primaryAgent().id;
    startAgentSeat(agentId).catch(() => {});
  });
  byId("aiDialerAgent-stopButton")?.addEventListener("click", () => {
    const agentId = S.aiDialerSelectedAgentId || primaryAgent().id;
    stopAgentSeat(agentId).catch(() => {});
  });
  byId("aiDialerAgent-claimPoolButton")?.addEventListener("click", async () => {
    const agentId = S.aiDialerSelectedAgentId || primaryAgent().id;
    if (agentId !== primaryAgent().id) {
      showToast("Only the live-line seat can claim a pool right now.", true);
      return;
    }
    try {
      const result = await postJson("/api/ai-agents/boot", { agent_id: agentId });
      mergeLiveState(result.state);
      await loadAppState();
      render();
      showToast(result.created ? "Agent pool claimed." : "Agent pool already assigned.");
    } catch (error) {
      showToast(errorText(error, "Could not claim pool."), true);
    }
  });
  byId("aiDialerAgent-releasePoolButton")?.addEventListener("click", async () => {
    const agentId = S.aiDialerSelectedAgentId || primaryAgent().id;
    if (!window.confirm("Remove every prospect from this agent pool and clear agent-use locks?")) return;
    try {
      const result = await postJson("/api/ai-agents/release-pool", { agent_id: agentId });
      mergeLiveState(result.state);
      await loadAppState();
      render();
      showToast(`Released ${result.released || 0} prospects.`);
    } catch (error) {
      showToast(errorText(error, "Could not release pool."), true);
    }
  });
  registerRenderer(renderAiDialerWorkspace);
  syncAiDialerViews();
}
