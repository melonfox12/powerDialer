/** Canonical workflow node templates (preview only — no runtime wiring yet). */

export const WORKFLOW_LANES = {
  prep: { label: "Prep", css: "lane-prep" },
  "ai-calling": { label: "AI calling", css: "lane-ai-calling" },
  decide: { label: "Decide", css: "lane-decide" },
  crm: { label: "CRM", css: "lane-crm" },
};

/**
 * @typedef {Object} WorkflowNodeTemplate
 * @property {string} id
 * @property {keyof WORKFLOW_LANES} lane
 * @property {string} title
 * @property {string} type
 * @property {string[]} outputs
 * @property {string} shows
 * @property {string} description
 */

/** @type {WorkflowNodeTemplate[]} */
export const WORKFLOW_NODE_TEMPLATES = [
  {
    id: "lead-list",
    lane: "prep",
    title: "Lead list",
    type: "Source",
    outputs: ["all leads"],
    shows: "list name, count, filters",
    description:
      "Entry source for a campaign list. Surfaces which list is active, how many leads are loaded, and any list filters applied before downstream prep.",
  },
  {
    id: "phone-lookup",
    lane: "prep",
    title: "Phone lookup",
    type: "Process",
    outputs: ["business line", "excluded"],
    shows: "line type results, invalid count",
    description:
      "Twilio-style line research step. Routes numbers into a business-line path vs excluded, and displays lookup breakdown plus invalid count.",
  },
  {
    id: "compliance-gate",
    lane: "prep",
    title: "Compliance gate",
    type: "Gate",
    outputs: ["pass", "hold", "blocked"],
    shows: "DNC hits, outside-hours holds, attempt caps",
    description:
      "Policy gate before dialing. Splits traffic into pass, hold, or blocked based on DNC, calling windows, and per-lead attempt caps.",
  },
  {
    id: "call-queue",
    lane: "ai-calling",
    title: "Call queue",
    type: "Queue",
    outputs: ["next to dial"],
    shows: "queue depth, next dial time",
    description:
      "Ordered queue of leads ready for the dialer. Shows how deep the queue is and when the next outbound attempt is scheduled.",
  },
  {
    id: "ai-calling-pool",
    lane: "ai-calling",
    title: "AI calling pool",
    type: "Pool",
    outputs: ["answered", "no answer", "other"],
    shows: "live agents out of 10, calls in progress",
    description:
      "Parallel AI dialer pool. Tracks active agents vs capacity and live calls, fanning results into answered, no answer, or other paths.",
  },
  {
    id: "outcome-router",
    lane: "decide",
    title: "Outcome router",
    type: "Router",
    outputs: ["answered", "retry", "excluded"],
    shows: "disposition breakdown",
    description:
      "Routes call outcomes into answered, retry, or excluded lanes and summarizes disposition mix for the current session.",
  },
  {
    id: "retry-scheduler",
    lane: "decide",
    title: "Retry scheduler",
    type: "Process",
    outputs: ["back to queue", "exhausted"],
    shows: "attempt number, next retry time",
    description:
      "Schedules follow-up attempts for retryable dispositions or marks leads exhausted when caps are met.",
  },
  {
    id: "qualify-prioritize",
    lane: "decide",
    title: "Qualify and prioritize",
    type: "Rules",
    outputs: ["qualified", "disqualified"],
    shows: "the rules applied, priority split (hot/warm/cold)",
    description:
      "Rules engine that qualifies leads and assigns hot, warm, or cold priority before CRM handoff.",
  },
  {
    id: "qualified-crm",
    lane: "crm",
    title: "Qualified to CRM",
    type: "End",
    outputs: ["callback queued"],
    shows: "notes, priority, owner, linked transcript",
    description:
      "CRM sink for qualified leads. Queues callbacks and shows notes, priority, owner, and transcript linkage.",
  },
  {
    id: "disqualified-crm",
    lane: "crm",
    title: "Disqualified to CRM",
    type: "End",
    outputs: ["recycle or closed"],
    shows: "reason, notes, recycle date",
    description:
      "CRM sink for disqualified leads with recycle-or-close outcome, reason, notes, and optional recycle date.",
  },
  {
    id: "excluded-crm",
    lane: "crm",
    title: "Excluded",
    type: "End",
    outputs: ["none"],
    shows: "reason breakdown (DNC, wrong number, mobile, invalid)",
    description:
      "Terminal path for leads removed from the dial stream, with a breakdown of DNC, wrong number, mobile, and invalid reasons.",
  },
];

const templateById = new Map(WORKFLOW_NODE_TEMPLATES.map((t) => [t.id, t]));

export function workflowTemplateById(id) {
  return templateById.get(id) ?? null;
}