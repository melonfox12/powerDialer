import { WORKFLOW_NODE_IDS } from "./transitions.js";

/** Bumps when default positions change (grid → chain, etc.). */
export const FIXED_CANVAS_MIGRATION_KEY = "godial-workflow-fixed-canvas-v2";

const NODE_W = 248;
const NODE_H = 148;
const NODE_GAP = 52;
const CHAIN_ORIGIN = { x: 48, y: 200 };

/** Default: one horizontal row in pipeline node order. */
function chainPositions() {
  /** @type {Record<string, { x: number, y: number, w: number, h: number }>} */
  const map = {};
  WORKFLOW_NODE_IDS.forEach((templateId, index) => {
    map[templateId] = {
      x: CHAIN_ORIGIN.x + index * (NODE_W + NODE_GAP),
      y: CHAIN_ORIGIN.y,
      w: NODE_W,
      h: NODE_H,
    };
  });
  return map;
}

export function runFixedCanvasMigration() {
  try {
    if (localStorage.getItem(FIXED_CANVAS_MIGRATION_KEY)) return;
    localStorage.removeItem("godial-workflow-instances");
    localStorage.removeItem("godial-workflow-edges");
    localStorage.removeItem("godial-workflow-layout");
    localStorage.removeItem("godial-workflow-fixed-canvas-v1");
    localStorage.setItem(FIXED_CANVAS_MIGRATION_KEY, "1");
  } catch {
    // ignore quota
  }
}

export function buildFixedWorkflowInstances() {
  const positions = chainPositions();
  return WORKFLOW_NODE_IDS.map((templateId) => {
    const pos = positions[templateId];
    return {
      id: templateId,
      templateId,
      x: pos.x,
      y: pos.y,
      w: pos.w,
      h: pos.h,
    };
  });
}

export function isFixedWorkflowNodeId(nodeId) {
  return WORKFLOW_NODE_IDS.includes(nodeId);
}