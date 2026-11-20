import { S, state } from "../../_core/state.js";
import { agentsList, agentById, primaryAgent } from "./agents.js";
import { duplicateAgentFromFleet, deleteAgentFromFleet } from "./agent-fleet-actions.js";
import { byId, setText } from "../../_core/format.js";
import { resetWorkspaceTabs, paintWorkspaceTabs } from "./workspace-tabs.js";
import { ensurePlaybookLoaded } from "./playbook-editor.js";

function agentStatus(agent) {
  if (!agent.primary) return { label: "Standby", tone: "idle" };
  if (state.pending_outcome) return { label: "Wrap-up", tone: "wrap" };
  if (state.active_lead) return { label: "Live call", tone: "live" };
  if (state.running) {
    const ringing = (state.in_flight || []).some((call) => call.state === "ringing");
    if (ringing) return { label: "Ringing", tone: "ringing" };
    if (!state.agent_ready) return { label: "Connecting", tone: "connecting" };
    return { label: "Dialing", tone: "dialing" };
  }
  return { label: "Off duty", tone: "idle" };
}

function todayMetrics(agent) {
  if (!agent.primary) return { dials: "—", connects: "—", booked: "—" };
  const today = state.metrics?.today || {};
  const stats = state.session_stats || {};
  const sessionDials = Number(stats.dials || 0);
  const sessionConnects = Number(stats.conversations || 0);
  return {
    dials: String(today.dials ?? sessionDials ?? 0),
    connects: String(today.connected ?? sessionConnects ?? 0),
    booked: String(today.booked ?? stats.meetings_booked ?? 0),
  };
}

let fleetSignature = "";

export function invalidateFleetGrid() {
  fleetSignature = "";
}

function renderFleetTiles() {
  const grid = byId("aiDialerAgent-fleetGrid");
  if (!grid) return;
  const signature = agentsList().map((agent) => {
    const status = agentStatus(agent);
    const metrics = todayMetrics(agent);
    return [agent.id, agent.name, status.label, metrics.dials, metrics.connects, state.running, state.active_lead?.id || ""].join("|");
  }).join("\x1e");
  if (signature === fleetSignature) return;
  fleetSignature = signature;
  grid.replaceChildren();
  for (const agent of agentsList()) {
    const status = agentStatus(agent);
    const metrics = todayMetrics(agent);
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = `ai-agent-tile ai-agent-tile--${status.tone}`;
    tile.dataset.agentId = agent.id;
    if (agent.primary) tile.classList.add("is-primary");
    const head = document.createElement("div");
    head.className = "ai-agent-tile-head";
    const name = document.createElement("strong");
    name.className = "ai-agent-tile-name";
    name.textContent = agent.name;
    const role = document.createElement("span");
    role.className = "ai-agent-tile-role";
    role.textContent = agent.title;
    head.append(name, role);
    const statusRow = document.createElement("div");
    statusRow.className = "ai-agent-tile-status";
    const dot = document.createElement("span");
    dot.className = "ai-agent-tile-dot";
    dot.setAttribute("aria-hidden", "true");
    const statusText = document.createElement("span");
    statusText.textContent = status.label;
    statusRow.append(dot, statusText);
    const stats = document.createElement("dl");
    stats.className = "ai-agent-tile-stats";
    const addStat = (term, value) => {
      const row = document.createElement("div");
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      row.append(dt, dd);
      stats.append(row);
    };
    addStat("Dials today", metrics.dials);
    addStat("Connects", metrics.connects);
    addStat("Booked", metrics.booked);
    const actions = document.createElement("div");
    actions.className = "ai-agent-tile-actions";
    const dup = document.createElement("button");
    dup.type = "button";
    dup.className = "button button-quiet ai-agent-tile-action";
    dup.textContent = "Duplicate";
    dup.addEventListener("click", (event) => duplicateAgentFromFleet(agent.id, event));
    const del = document.createElement("button");
    del.type = "button";
    del.className = "button button-quiet ai-agent-tile-action";
    del.textContent = "Delete";
    del.addEventListener("click", (event) => deleteAgentFromFleet(agent.id, event));
    actions.append(dup, del);
    tile.append(head, statusRow, stats, actions);
    if (agent.primary) {
      const badge = document.createElement("span");
      badge.className = "ai-agent-tile-badge";
      badge.textContent = "Live line";
      tile.append(badge);
    }
    tile.addEventListener("click", () => {
      S.aiDialerSelectedAgentId = agent.id;
      resetWorkspaceTabs();
      paintWorkspaceTabs();
      ensurePlaybookLoaded(agent.id).catch(() => {});
      syncAiDialerViews();
    });
    grid.append(tile);
  }
}

export function syncAiDialerViews() {
  const fleet = byId("aiDialerAgent-fleetView");
  const detail = byId("aiDialerAgent-detailView");
  const onAiTab = S.dashboardTab === "aiDialerAgent";
  const agentId = S.aiDialerSelectedAgentId;
  const showFleet = onAiTab && !agentId;
  if (fleet) fleet.hidden = !showFleet;
  if (detail) detail.hidden = !onAiTab || !agentId;
  const panel = byId("aiDialerAgentTabPanel");
  if (panel) panel.classList.toggle("ai-call-center--fleet", showFleet);
  if (panel) panel.classList.toggle("ai-call-center--detail", Boolean(agentId && onAiTab));
  const agent = agentById(agentId);
  const title = byId("aiDialerAgent-detailAgentName");
  const subtitle = byId("aiDialerAgent-detailAgentTitle");
  if (title) title.textContent = agent?.name || "Agent";
  if (subtitle) subtitle.textContent = agent?.title || "AI dialer";
}

export function renderAiDialerFleet() {
  if (S.dashboardTab !== "aiDialerAgent") return;
  syncAiDialerViews();
  if (!S.aiDialerSelectedAgentId) renderFleetTiles();
}

function agentMeta(agentId) {
  return (state.ai_agents?.agents || []).find((item) => item.id === agentId) || null;
}

export function renderAiAgentDetailStats(agentId) {
  const agent = agentById(agentId);
  const meta = agentMeta(agentId);
  const poolTotal = meta?.pool_size ?? state.agent_pool_total ?? (state.ai_agents?.agent_pools?.[agentId] || []).length ?? 0;
  const poolDialable = meta?.pool_dialable ?? state.agent_pool_dialable ?? 0;
  setText("aiDialerAgent-globalPoolCount", String(state.global_dialer_pool_count ?? state.global_dialer_pool?.length ?? 0));
  setText("aiDialerAgent-agentPoolCount", String(poolTotal));
  const dials = Number(state.session_stats?.dials || 0);
  const lineText = poolTotal > 0 ? `${dials} of ${poolTotal} dialed` : "0 of 0 dialed";
  setText("aiDialerAgent-lineCount", lineText);
  const start = byId("aiDialerAgent-startButton");
  if (start) {
    const canStart = poolTotal > 0 && poolDialable > 0 && !state.running;
    start.disabled = !canStart || state.running;
    start.title = poolDialable > 0 ? "" : "Claim a pool with at least one dialable prospect before starting.";
  }
  const detail = byId("aiDialerAgent-detailView");
  detail?.classList.toggle("ai-dial-starved", Boolean(state.ai_dial_starved && state.running));
  const liveStatus = byId("aiDialerAgent-dialerStatusHeadline");
  if (liveStatus) {
    const { label } = agent?.primary ? agentStatus(agent) : { label: "Standby" };
    const target = state.active_lead?.name || state.active_lead?.business || state.last_event || label;
    const runningThis = state.ai_agents?.running_agent_id === agentId && state.running;
    liveStatus.textContent = state.active_lead && runningThis
      ? `On the line · ${target}`
      : runningThis && state.ai_dial_starved
        ? "Waiting for more numbers in agent pool"
        : runningThis
          ? label
          : poolTotal < 1
            ? "Claim a pool before starting"
            : poolDialable < 1
              ? "Pool has no dialable prospects"
              : agent?.primary
                ? "Ready to start"
                : "Seat not wired yet";
  }
}
