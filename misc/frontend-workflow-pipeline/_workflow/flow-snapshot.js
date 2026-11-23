/** In-memory campaign flow counts (set by campaign-flow.js). No imports from campaign chrome. */

/** @type {object | null} */
let snapshot = null;

export function setFlowSnapshot(next) {
  snapshot = next;
}

export function getFlowSnapshot() {
  return snapshot;
}

export function nodeLeadCount(nodeId) {
  return snapshot?.nodes?.[nodeId]?.count ?? 0;
}

export function edgeLeadCount(edgeId) {
  return snapshot?.edges?.[edgeId]?.count ?? 0;
}

export function nodeLeadIds(nodeId) {
  const row = snapshot?.nodes?.[nodeId];
  return Array.isArray(row?.lead_ids) ? row.lead_ids : [];
}

/**
 * @param {{ id?: string, from?: string, to?: string }} edge
 */
export function canvasEdgeLeadIds(edge) {
  if (!edge) return [];
  if (typeof edge.id === "string" && edge.id.startsWith("e-chain:")) {
    return nodeLeadIds(edge.from || "");
  }
  return Array.isArray(snapshot?.edges?.[edge.id]?.lead_ids) ? snapshot.edges[edge.id].lead_ids : [];
}