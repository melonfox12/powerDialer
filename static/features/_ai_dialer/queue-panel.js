import { state } from "../../_core/state.js";
import { agentById } from "./agents.js";
import { byId } from "../../_core/format.js";

let lastQueueKey = "";

export function renderAgentQueueList(agentId) {
  const list = byId("aiDialerAgent-agentQueueList");
  if (!list) return;
  const pools = state.ai_agents?.agent_pools || {};
  const ids = pools[agentId] || [];
  const running = state.ai_agents?.running_agent_id === agentId && state.running;
  const queueIds = running ? (state.pool || []).map((lead) => lead.id) : [];
  const key = JSON.stringify([agentId, ids, queueIds, state.leads_version]);
  if (key === lastQueueKey) return;
  lastQueueKey = key;
  list.replaceChildren();
  if (!ids.length) {
    const item = document.createElement("li");
    item.className = "ai-agent-queue-empty";
    item.textContent = "Boot the agent to claim up to 50 prospects from the global pool.";
    list.append(item);
    return;
  }
  const byIdMap = Object.fromEntries((state.leads || []).map((lead) => [lead.id, lead]));
  const cap = 12;
  for (const leadId of ids.slice(0, cap)) {
    const lead = byIdMap[leadId];
    const item = document.createElement("li");
    const active = queueIds.includes(leadId) || state.active_lead?.id === leadId;
    item.className = active ? "is-active" : "";
    item.textContent = lead?.name || lead?.business || leadId;
    list.append(item);
  }
  if (ids.length > cap) {
    const more = document.createElement("li");
    more.className = "ai-agent-queue-more";
    more.textContent = `+${ids.length - cap} more in pool`;
    list.append(more);
  }
}
