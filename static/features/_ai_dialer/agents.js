/** Named AI dialer seats. Only `primary` agents bind to the live server session until multi-session ships. */
export const AI_AGENTS = [
  { id: "ava", name: "Ava", title: "Appointment setter", primary: true },
  { id: "miles", name: "Miles", title: "Appointment setter" },
  { id: "riley", name: "Riley", title: "Qualification" },
  { id: "jordan", name: "Jordan", title: "Appointment setter" },
  { id: "casey", name: "Casey", title: "Follow-up" },
  { id: "morgan", name: "Morgan", title: "Appointment setter" },
  { id: "quinn", name: "Quinn", title: "Reception bridge" },
  { id: "skyler", name: "Skyler", title: "Appointment setter" },
];

export function agentById(id) {
  return AI_AGENTS.find((item) => item.id === id) || null;
}

export function primaryAgent() {
  return AI_AGENTS.find((item) => item.primary) || AI_AGENTS[0];
}
