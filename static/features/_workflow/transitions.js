/** Fixed workflow graph (keep in sync with features/_campaigns/transitions.py). */

export const WORKFLOW_ENTRY_NODE = "lead-list";

/** @type {readonly string[]} */
export const WORKFLOW_NODE_IDS = [
  "lead-list",
  "phone-lookup",
  "compliance-gate",
  "call-queue",
  "dialing",
  "in-conversation",
  "outcome-router",
  "retry-scheduler",
  "qualify-prioritize",
  "qualified-crm",
  "disqualified-crm",
  "excluded-crm",
];

/**
 * @typedef {{
 *   id: string,
 *   from: string,
 *   to: string,
 *   fromSocket: string,
 *   toSocket: string,
 *   lane?: number,
 * }} WorkflowFixedEdge
 */

/** @type {WorkflowFixedEdge[]} */
export const WORKFLOW_FIXED_EDGES = [
  { id: "e-lead-phone", from: "lead-list", to: "phone-lookup", fromSocket: "out", toSocket: "in" },
  {
    id: "e-phone-compliance",
    from: "phone-lookup",
    to: "compliance-gate",
    fromSocket: "out-business-line",
    toSocket: "in",
  },
  { id: "e-phone-excluded", from: "phone-lookup", to: "excluded-crm", fromSocket: "out-excluded", toSocket: "in" },
  { id: "e-compliance-queue", from: "compliance-gate", to: "call-queue", fromSocket: "out-pass", toSocket: "in" },
  {
    id: "e-compliance-excluded",
    from: "compliance-gate",
    to: "excluded-crm",
    fromSocket: "out-blocked",
    toSocket: "in",
  },
  { id: "e-queue-dialing", from: "call-queue", to: "dialing", fromSocket: "out", toSocket: "in" },
  {
    id: "e-dialing-conversation",
    from: "dialing",
    to: "in-conversation",
    fromSocket: "out-answered",
    toSocket: "in",
  },
  {
    id: "e-dialing-outcome",
    from: "dialing",
    to: "outcome-router",
    fromSocket: "out-no-answer-vm-failed",
    toSocket: "in",
  },
  { id: "e-conversation-outcome", from: "in-conversation", to: "outcome-router", fromSocket: "out", toSocket: "in" },
  { id: "e-outcome-retry", from: "outcome-router", to: "retry-scheduler", fromSocket: "out-retry", toSocket: "in" },
  {
    id: "e-outcome-qualify",
    from: "outcome-router",
    to: "qualify-prioritize",
    fromSocket: "out-answered",
    toSocket: "in",
  },
  {
    id: "e-outcome-disqualified",
    from: "outcome-router",
    to: "disqualified-crm",
    fromSocket: "out-disqualified",
    toSocket: "in",
  },
  { id: "e-outcome-excluded", from: "outcome-router", to: "excluded-crm", fromSocket: "out-excluded", toSocket: "in" },
  {
    id: "e-retry-queue",
    from: "retry-scheduler",
    to: "call-queue",
    fromSocket: "out-back-to-queue",
    toSocket: "in",
  },
  {
    id: "e-qualify-qualified",
    from: "qualify-prioritize",
    to: "qualified-crm",
    fromSocket: "out-qualified",
    toSocket: "in",
  },
];

/** Map API edge_list rows to canvas edge shape. */
export function mapFlowEdgesToCanvas(edgeList) {
  const source = edgeList?.length ? edgeList : WORKFLOW_FIXED_EDGES;
  return source.map((row, index) => ({
    id: row.id,
    from: row.from,
    to: row.to,
    fromSocket: row.from_socket || row.fromSocket,
    toSocket: row.to_socket || row.toSocket,
    lane: row.lane ?? (index % 3) - 1,
  }));
}