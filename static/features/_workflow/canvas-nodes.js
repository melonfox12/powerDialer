import { buildWorkflowNodeElement } from "./node-factory.js";
import { buildFixedWorkflowInstances, runFixedCanvasMigration } from "./fixed-canvas.js";

export const INSTANCES_KEY = "godial-workflow-instances";
export const EDGES_KEY = "godial-workflow-edges";
const MIGRATION_KEY = "godial-workflow-catalog-v2-reset";
const LEGACY_LAYOUT_KEY = "godial-workflow-layout";
const LEGACY_SOCKET_KEY = "godial-workflow-socket-layout";
const LEGACY_OFFICE_KEY = "godial-workflow-office-seats";

/**
 * @typedef {{ id: string, templateId: string, x: number, y: number, w?: number, h?: number }} WorkflowInstance
 */

/** @type {WorkflowInstance[]} */
let instances = [];

function newInstanceId() {
  return `wf-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export function runWorkflowCanvasMigration() {
  try {
    if (localStorage.getItem(MIGRATION_KEY)) return;
    localStorage.removeItem(LEGACY_LAYOUT_KEY);
    localStorage.removeItem(LEGACY_SOCKET_KEY);
    localStorage.removeItem(LEGACY_OFFICE_KEY);
    localStorage.setItem(INSTANCES_KEY, "[]");
    localStorage.setItem(EDGES_KEY, "[]");
    localStorage.setItem(MIGRATION_KEY, "1");
  } catch {
    // ignore quota
  }
}

function expectedNodeIdSet() {
  return new Set(buildFixedWorkflowInstances().map((row) => row.id));
}

export function loadWorkflowInstances() {
  runWorkflowCanvasMigration();
  runFixedCanvasMigration();
  const defaults = buildFixedWorkflowInstances();
  const defaultById = new Map(defaults.map((row) => [row.id, row]));
  const expected = expectedNodeIdSet();
  try {
    const raw = JSON.parse(localStorage.getItem(INSTANCES_KEY) || "[]");
    if (Array.isArray(raw) && raw.length === expected.size) {
      const rows = raw.filter(
        (row) =>
          row?.id &&
          row?.templateId &&
          expected.has(row.id) &&
          Number.isFinite(row.x) &&
          Number.isFinite(row.y),
      );
      if (rows.length === expected.size) {
        instances = rows.map((row) => ({
          ...defaultById.get(row.id),
          ...row,
          id: row.id,
          templateId: row.templateId,
        }));
        return instances;
      }
    }
  } catch {
    // fall through to defaults
  }
  instances = defaults;
  saveWorkflowInstances();
  return instances;
}

export function saveWorkflowInstances() {
  try {
    localStorage.setItem(INSTANCES_KEY, JSON.stringify(instances));
  } catch {
    // ignore
  }
}

export function getWorkflowInstances() {
  return instances;
}

export function getWorkflowLayoutMap() {
  /** @type {Record<string, { x: number, y: number }>} */
  const map = {};
  for (const row of instances) {
    map[row.id] = { x: row.x, y: row.y };
  }
  return map;
}

export function getWorkflowSizeMap() {
  /** @type {Record<string, { w?: number, h?: number }>} */
  const map = {};
  for (const row of instances) {
    if (row.w || row.h) map[row.id] = { w: row.w, h: row.h };
  }
  return map;
}

export function updateInstancePosition(id, x, y) {
  const row = instances.find((r) => r.id === id);
  if (!row) return;
  row.x = x;
  row.y = y;
}

export function updateInstanceSize(id, w, h) {
  const row = instances.find((r) => r.id === id);
  if (!row) return;
  if (w) row.w = Math.round(w);
  if (h) row.h = Math.round(h);
}

/**
 * @param {string} templateId
 * @param {number} x
 * @param {number} y
 */
export function addWorkflowInstance(templateId, x, y) {
  const row = { id: newInstanceId(), templateId, x, y };
  instances.push(row);
  saveWorkflowInstances();
  return row;
}

export function removeWorkflowInstance(id) {
  instances = instances.filter((r) => r.id !== id);
  saveWorkflowInstances();
}

export function mountWorkflowInstances(layer) {
  if (!layer) return;
  layer.replaceChildren();
  for (const row of instances) {
    const node = buildWorkflowNodeElement(row.id, row.templateId, { w: row.w, h: row.h });
    if (node) layer.appendChild(node);
  }
}

export function loadWorkflowEdges() {
  try {
    const raw = JSON.parse(localStorage.getItem(EDGES_KEY) || "[]");
    return Array.isArray(raw) ? raw : [];
  } catch {
    return [];
  }
}

export function saveWorkflowEdges(edges) {
  try {
    localStorage.setItem(EDGES_KEY, JSON.stringify(edges));
  } catch {
    // ignore
  }
}