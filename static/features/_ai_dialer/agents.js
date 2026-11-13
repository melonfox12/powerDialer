import { state } from "../../_core/state.js";

const FALLBACK_AGENTS = [
  { id: "ava", name: "Ava", title: "Appointment setter", primary: true },
  { id: "miles", name: "Miles", title: "Appointment setter", primary: false },
  { id: "riley", name: "Riley", title: "Qualification", primary: false },
  { id: "jordan", name: "Jordan", title: "Appointment setter", primary: false },
  { id: "casey", name: "Casey", title: "Follow-up", primary: false },
  { id: "morgan", name: "Morgan", title: "Appointment setter", primary: false },
  { id: "quinn", name: "Quinn", title: "Reception bridge", primary: false },
  { id: "skyler", name: "Skyler", title: "Appointment setter", primary: false },
];

export function agentsList() {
  const fromServer = state.ai_agents?.agents;
  if (Array.isArray(fromServer) && fromServer.length) {
    return fromServer.map((item) => ({
      id: item.id,
      name: item.name,
      title: item.title || "AI dialer",
      primary: Boolean(item.primary),
    }));
  }
  return FALLBACK_AGENTS;
}

/** @deprecated use agentsList() */
export const AI_AGENTS = FALLBACK_AGENTS;

export function agentById(id) {
  return agentsList().find((item) => item.id === id) || null;
}

export function primaryAgent() {
  return agentsList().find((item) => item.primary) || agentsList()[0];
}
