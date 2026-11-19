import { registerRenderer } from "../_core/registry.js";
import {
  getWorkflowInstances,
  getWorkflowLayoutMap,
  loadWorkflowInstances,
  mountWorkflowInstances,
  saveWorkflowInstances,
  updateInstancePosition,
  updateInstanceSize,
} from "./_workflow/canvas-nodes.js";
import {
  bindCampaignFlow,
  edgeLeadCount,
  getCampaignFlowSnapshot,
  refreshCampaignFlow,
} from "./_workflow/campaign-flow.js";
import { paintWorkflowNodeCounts } from "./_workflow/node-counts.js";
import { mapFlowEdgesToCanvas, WORKFLOW_FIXED_EDGES } from "./_workflow/transitions.js";
import { buildWorkflowNodeElement } from "./_workflow/node-factory.js";
import { bindWorkflowConnections, isWorkflowWiring } from "./_workflow/connections.js";
import { bindCampaignChrome, refreshCampaignCatalog } from "./_workflow/campaign-chrome.js";
import { bindCampaignImportDialog } from "./_workflow/campaign-import.js";
import {
  bindWorkflowCrmSidebar,
  releaseWorkflowCrmSidebarDom,
  renderWorkflowCrmSidebar,
} from "./_workflow/campaign-crm-sidebar.js";
import {
  applySocketLayouts,
  bindWorkflowTools,
  loadSocketLayout,
  socketCenterOnNode,
  workflowToolBlocksNodeDrag,
} from "./_workflow/tools.js";

const CAMERA_KEY = "godial-workflow-camera";
const MIN_CANVAS_W = 2280;
const MIN_CANVAS_H = 920;
const MAX_SPAN_W = 24000;
const MAX_SPAN_H = 16000;
const LOGICAL_COORD_LIMIT = 30000;
const CANVAS_PAD = 180;
const ZOOM_INTENSITY = 0.00115;
const TRACKPAD_ZOOM_INTENSITY = 0.0085;
const MIN_SCALE = 0.22;
const MAX_SCALE = 2.75;
const WHEEL_DELTA_PIXEL = 0;
const WHEEL_DELTA_LINE = 1;
const WHEEL_LINE_TO_PX = 16;
const PAN_VELOCITY_WINDOW_MS = 110;
const PAN_RELEASE_GAIN = 0.78;
const PAN_MAX_SPEED = 2.05;
const PAN_MIN_SPEED = 0.09;
const PAN_DECAY_PER_SEC = 5.4;
const DRAG_EDGE_INSET = 52;
/** Max viewport pan speed (px/s) when pushing a node past the screen edge */
const DRAG_EDGE_PAN_MAX = 190;
const DRAG_EDGE_FRAME_MS = 16;

/** @type {{ from: string, fromSocket: string, to: string, toSocket: string, lane?: number }[]} */
let EDGES = [];

const DEFAULT_CAMERA = { panX: 24, panY: 20, scale: 0.92 };

/** @type {Record<string, { x: number, y: number }>} */
let layout = {};
let camera = { ...DEFAULT_CAMERA };
let dragState = null;
let panState = null;
let panInertia = null;
let panInertiaFrame = 0;
let bound = false;
/** Top-left of the scrollable workspace in logical coordinates (can be negative). */
let canvasOrigin = { x: 0, y: 0 };
let workspaceBoundsReady = false;
let panCameraFrameQueued = false;
let dragEdgeFrame = 0;
let lastDragPointer = { x: 0, y: 0 };
let workflowFrameQueued = false;
let wheelPanAccum = { dx: 0, dy: 0 };
let wheelPanRaf = 0;
let lastSurfaceW = 0;
let lastSurfaceH = 0;
/** @type {SVGPathElement[]} */
let edgePathEls = [];
/** @type {SVGLineElement[]} */
let edgeOutCapEls = [];
/** @type {SVGPolygonElement[]} */
let edgeInArrowEls = [];
/** @type {SVGTextElement[]} */
let edgeCountLabelEls = [];
const SVG_NS = "http://www.w3.org/2000/svg";

function viewport() {
  return document.getElementById("workflowViewport");
}

function world() {
  return document.getElementById("workflowWorld");
}

function nodeLayer() {
  return document.getElementById("workflowNodeLayer");
}

function edgesSvg() {
  return document.getElementById("workflowEdges");
}

function arrowsSvg() {
  return document.getElementById("workflowEdgeArrows");
}

function loadFixedEdges() {
  const snap = getCampaignFlowSnapshot();
  EDGES = mapFlowEdgesToCanvas(snap?.edge_list || WORKFLOW_FIXED_EDGES);
}

function loadLayout() {
  loadWorkflowInstances();
  layout = getWorkflowLayoutMap();
  loadFixedEdges();
  try {
    const savedCam = JSON.parse(localStorage.getItem(CAMERA_KEY) || "{}");
    camera = { ...DEFAULT_CAMERA, ...savedCam };
    camera.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, camera.scale));
  } catch {
    camera = { ...DEFAULT_CAMERA };
  }
}

function saveLayout() {
  for (const row of getWorkflowInstances()) {
    const pos = layout[row.id];
    if (pos) updateInstancePosition(row.id, pos.x, pos.y);
  }
  saveWorkflowInstances();
}

function saveCamera() {
  try {
    localStorage.setItem(CAMERA_KEY, JSON.stringify(camera));
  } catch {
    // ignore quota
  }
}

function defaultNodeSize(node) {
  const id = node?.dataset?.workflowNode;
  const inst = id ? getWorkflowInstances().find((row) => row.id === id) : null;
  const w = node?.offsetWidth || inst?.w || 268;
  const h = node?.offsetHeight || inst?.h || (node?.classList.contains("workflow-node--sized") ? 160 : undefined);
  return { w, h: h || 160 };
}

function syncCanvasOriginDataset() {
  const el = world();
  if (!el) return;
  el.dataset.canvasOriginX = String(canvasOrigin.x);
  el.dataset.canvasOriginY = String(canvasOrigin.y);
}

function appendInstanceNode(row) {
  const layer = nodeLayer();
  if (!layer || !row) return;
  const node = buildWorkflowNodeElement(row.id, row.templateId, { w: row.w, h: row.h });
  if (!node) return;
  layout[row.id] = { x: row.x, y: row.y };
  layer.appendChild(node);
  applySocketLayouts();
  scheduleWorkflowFrame();
}

function clampLogicalCoord(value) {
  return Math.max(-LOGICAL_COORD_LIMIT, Math.min(LOGICAL_COORD_LIMIT, value));
}

function measureContentBounds() {
  const layer = nodeLayer();
  if (!layer) {
    return { minX: 0, minY: 0, maxX: MIN_CANVAS_W, maxY: MIN_CANVAS_H };
  }
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let found = false;
  for (const node of layer.querySelectorAll("[data-workflow-node]")) {
    const id = node.dataset.workflowNode;
    const pos = layout[id];
    if (!pos) continue;
    found = true;
    const size = defaultNodeSize(node);
    const w = node.offsetWidth || size.w;
    const h = node.offsetHeight || size.h;
    minX = Math.min(minX, pos.x);
    minY = Math.min(minY, pos.y);
    maxX = Math.max(maxX, pos.x + w);
    maxY = Math.max(maxY, pos.y + h);
  }
  if (!found) {
    return { minX: 0, minY: 0, maxX: MIN_CANVAS_W, maxY: MIN_CANVAS_H };
  }
  minX -= CANVAS_PAD;
  minY -= CANVAS_PAD;
  maxX += CANVAS_PAD;
  maxY += CANVAS_PAD;
  if (maxX - minX < MIN_CANVAS_W) {
    const mid = (maxX + minX) / 2;
    minX = mid - MIN_CANVAS_W / 2;
    maxX = mid + MIN_CANVAS_W / 2;
  }
  if (maxY - minY < MIN_CANVAS_H) {
    const mid = (maxY + minY) / 2;
    minY = mid - MIN_CANVAS_H / 2;
    maxY = mid + MIN_CANVAS_H / 2;
  }
  return { minX, minY, maxX, maxY };
}

function updateWorkspaceBounds() {
  const prevOriginX = canvasOrigin.x;
  const prevOriginY = canvasOrigin.y;
  const { minX, minY, maxX, maxY } = measureContentBounds();
  canvasOrigin = { x: minX, y: minY };
  const dx = canvasOrigin.x - prevOriginX;
  const dy = canvasOrigin.y - prevOriginY;
  if ((dx || dy) && (dragState || workspaceBoundsReady)) {
    camera.panX += dx * camera.scale;
    camera.panY += dy * camera.scale;
    applyCamera();
  }
  workspaceBoundsReady = true;
  syncCanvasOriginDataset();
  const w = Math.min(MAX_SPAN_W, Math.max(MIN_CANVAS_W, maxX - minX));
  const h = Math.min(MAX_SPAN_H, Math.max(MIN_CANVAS_H, maxY - minY));
  for (const el of [world(), nodeLayer(), edgesSvg(), arrowsSvg()]) {
    if (!el) continue;
    el.style.width = `${w}px`;
    el.style.height = `${h}px`;
  }
  return { w, h };
}

function applyCamera() {
  const el = world();
  if (!el) return;
  el.style.transform = `translate3d(${camera.panX}px, ${camera.panY}px, 0) scale(${camera.scale})`;
  const layer = nodeLayer();
  const svg = edgesSvg();
  const arrowLayer = arrowsSvg();
  if (layer) layer.style.transform = "";
  if (svg) svg.style.transform = "";
  if (arrowLayer) arrowLayer.style.transform = "";
}

function applyPanCameraFromState() {
  if (!panState) return;
  camera.panX = panState.originPanX + (panState.latestX - panState.originX);
  camera.panY = panState.originPanY + (panState.latestY - panState.originY);
  applyCamera();
}

function schedulePanCameraApply() {
  if (panCameraFrameQueued) return;
  panCameraFrameQueued = true;
  requestAnimationFrame(() => {
    panCameraFrameQueued = false;
    applyPanCameraFromState();
  });
}

function stopPanInertia() {
  if (panInertiaFrame) cancelAnimationFrame(panInertiaFrame);
  panInertiaFrame = 0;
  panInertia = null;
  viewport()?.classList.remove("is-gliding");
  syncWorkflowInteractionClass();
}

function pushPanSample(samples, clientX, clientY) {
  const now = performance.now();
  samples.push({ x: clientX, y: clientY, t: now });
  while (samples.length > 1 && now - samples[0].t > PAN_VELOCITY_WINDOW_MS) samples.shift();
}

function panReleaseVelocity(samples) {
  if (!samples || samples.length < 2) return { vx: 0, vy: 0 };
  const first = samples[0];
  const last = samples[samples.length - 1];
  const dt = last.t - first.t;
  if (dt < 10) return { vx: 0, vy: 0 };
  let vx = ((last.x - first.x) / dt) * PAN_RELEASE_GAIN;
  let vy = ((last.y - first.y) / dt) * PAN_RELEASE_GAIN;
  const speed = Math.hypot(vx, vy);
  if (speed < PAN_MIN_SPEED * 0.55) return { vx: 0, vy: 0 };
  if (speed > PAN_MAX_SPEED) {
    const clamp = PAN_MAX_SPEED / speed;
    vx *= clamp;
    vy *= clamp;
  }
  return { vx, vy };
}

function startPanInertia(vx, vy) {
  stopPanInertia();
  if (Math.hypot(vx, vy) < PAN_MIN_SPEED) return;
  panInertia = { vx, vy, lastT: performance.now() };
  viewport()?.classList.add("is-gliding");
  syncWorkflowInteractionClass();
  const tick = (now) => {
    if (!panInertia) return;
    const dt = Math.min(40, now - panInertia.lastT);
    panInertia.lastT = now;
    const decay = Math.exp(-PAN_DECAY_PER_SEC * (dt / 1000));
    panInertia.vx *= decay;
    panInertia.vy *= decay;
    camera.panX += panInertia.vx * dt;
    camera.panY += panInertia.vy * dt;
    applyCamera();
    if (Math.hypot(panInertia.vx, panInertia.vy) < PAN_MIN_SPEED) {
      stopPanInertia();
      saveCamera();
      return;
    }
    panInertiaFrame = requestAnimationFrame(tick);
  };
  panInertiaFrame = requestAnimationFrame(tick);
}

function growWorkspaceDuringDragIfNeeded() {
  const layer = nodeLayer();
  if (!layer || !dragState) return;
  const pos = layout[dragState.id];
  if (!pos) return;
  const size = defaultNodeSize(dragState.node);
  const nw = dragState.node.offsetWidth || size.w;
  const nh = dragState.node.offsetHeight || size.h;
  const frozen = dragState.frozenOrigin;
  const needW = pos.x - frozen.x + nw + CANVAS_PAD;
  const needH = pos.y - frozen.y + nh + CANVAS_PAD;
  const prevW = Number.parseFloat(layer.style.width) || MIN_CANVAS_W;
  const prevH = Number.parseFloat(layer.style.height) || MIN_CANVAS_H;
  const w = Math.min(MAX_SPAN_W, Math.max(MIN_CANVAS_W, prevW, needW));
  const h = Math.min(MAX_SPAN_H, Math.max(MIN_CANVAS_H, prevH, needH));
  if (w === prevW && h === prevH) return;
  for (const el of [world(), nodeLayer(), edgesSvg(), arrowsSvg()]) {
    if (!el) continue;
    el.style.width = `${w}px`;
    el.style.height = `${h}px`;
  }
}

function workflowViewportInteracting() {
  return Boolean(dragState || panState || panInertia || isWorkflowWiring());
}

function resetEdgeGraphicElements() {
  edgePathEls = [];
  edgeOutCapEls = [];
  edgeInArrowEls = [];
  edgeCountLabelEls = [];
}

function layerPointFromClient(clientX, clientY) {
  const w = clientToWorld(clientX, clientY);
  return { x: w.x - canvasOrigin.x, y: w.y - canvasOrigin.y };
}

function buildWirePathD(x1, y1, x2, y2) {
  return edgePath(x1, y1, x2, y2);
}

function tryAddWorkflowEdge() {
  return false;
}

function syncWorkflowInteractionClass() {
  viewport()?.classList.toggle("is-workflow-interacting", workflowViewportInteracting());
}

function applyLayout() {
  const layer = nodeLayer();
  if (!layer) return;
  if (dragState) {
    canvasOrigin = dragState.frozenOrigin;
    growWorkspaceDuringDragIfNeeded();
    const pos = layout[dragState.id];
    if (pos) {
      dragState.node.style.left = `${pos.x - canvasOrigin.x}px`;
      dragState.node.style.top = `${pos.y - canvasOrigin.y}px`;
    }
    return;
  }
  updateWorkspaceBounds();
  for (const node of layer.querySelectorAll("[data-workflow-node]")) {
    const id = node.dataset.workflowNode;
    const pos = layout[id];
    if (!pos) continue;
    node.style.left = `${pos.x - canvasOrigin.x}px`;
    node.style.top = `${pos.y - canvasOrigin.y}px`;
  }
  applySocketLayouts();
}

function viewportRect() {
  return viewport()?.getBoundingClientRect();
}

function clientToWorld(clientX, clientY) {
  const rect = viewportRect();
  if (!rect) return { x: 0, y: 0 };
  const displayX = (clientX - rect.left - camera.panX) / camera.scale;
  const displayY = (clientY - rect.top - camera.panY) / camera.scale;
  return {
    x: displayX + canvasOrigin.x,
    y: displayY + canvasOrigin.y,
  };
}

function socketPoint(nodeId, socketName) {
  const layer = nodeLayer();
  if (!layer) return null;
  const node = layer.querySelector(`[data-workflow-node="${nodeId}"]`);
  if (!node) return null;
  const local = socketCenterOnNode(nodeId, socketName, node);
  if (!local) return null;

  const pos = layout[nodeId];
  const nodeLeft = pos ? pos.x - canvasOrigin.x : Number.parseFloat(node.style.left) || 0;
  const nodeTop = pos ? pos.y - canvasOrigin.y : Number.parseFloat(node.style.top) || 0;

  return {
    x: nodeLeft + local.x,
    y: nodeTop + local.y,
  };
}

/** Arrow tip / hidden socket hit target in layout pixels */
const WORKFLOW_ANCHOR_RADIUS = 6;
const WORKFLOW_ARROW_BACK = WORKFLOW_ANCHOR_RADIUS + 5;
/** Half-width at arrow base; mid-span width = this value (must stay < anchor radius). */
const WORKFLOW_ARROW_HALF_W = WORKFLOW_ANCHOR_RADIUS - 1;
/** Output: white highlight along the node edge (half-length each side of anchor). */
const WORKFLOW_OUTPUT_CAP_HALF = 12;
/** Connector leaves the output anchor this far along the outward ray. */
const WORKFLOW_OUTPUT_LINE_TRIM = 3;

function edgeBezierControls(x1, y1, x2, y2, lane = 0) {
  const horizontal = Math.max(64, Math.abs(x2 - x1) * 0.48);
  const bend = lane * 16;
  return {
    horizontal,
    bend,
    bx1: x1 + horizontal,
    by1: y1 + bend,
    bx2: x2 - horizontal,
    by2: y2 + bend,
  };
}

function edgeTangentAngleAtEnd(x1, y1, x2, y2, lane = 0) {
  const { bx2, by2 } = edgeBezierControls(x1, y1, x2, y2, lane);
  return Math.atan2(y2 - by2, x2 - bx2);
}

function nodeBlockCenter(nodeId) {
  const layer = nodeLayer();
  if (!layer) return null;
  const node = layer.querySelector(`[data-workflow-node="${nodeId}"]`);
  if (!node) return null;
  const pos = layout[nodeId];
  if (!pos) return null;
  const nodeLeft = pos.x - canvasOrigin.x;
  const nodeTop = pos.y - canvasOrigin.y;
  const ww = node.offsetWidth;
  const hh = node.offsetHeight;
  if (!ww || !hh) return null;
  return { x: nodeLeft + ww / 2, y: nodeTop + hh / 2 };
}

function edgeTangentAngleAtStart(x1, y1, x2, y2, lane = 0) {
  const { bx1, by1 } = edgeBezierControls(x1, y1, x2, y2, lane);
  return Math.atan2(by1 - y1, bx1 - x1);
}

/** From node center through anchor toward the outside of the block. */
function edgeOutwardFromNodeCenter(anchorX, anchorY, nodeId) {
  const center = nodeBlockCenter(nodeId);
  if (!center) return null;
  return Math.atan2(anchorY - center.y, anchorX - center.x);
}

function anchorOutwardAngle(ax, ay, nodeId, x1, y1, x2, y2, lane, atEnd) {
  return (
    edgeOutwardFromNodeCenter(ax, ay, nodeId) ??
    (atEnd ? edgeTangentAngleAtEnd(x1, y1, x2, y2, lane) : edgeTangentAngleAtStart(x1, y1, x2, y2, lane))
  );
}

function edgePath(x1, y1, x2, y2, lane = 0, trimStart = 0, trimEnd = 0, outwardStart = 0, outwardEnd = 0) {
  let { bx1, by1, bx2, by2, horizontal } = edgeBezierControls(x1, y1, x2, y2, lane);
  let sx = x1;
  let sy = y1;
  let ex = x2;
  let ey = y2;
  const ctrlLen = Math.max(52, horizontal * 0.75);

  if (trimStart > 0) {
    sx = x1 + Math.cos(outwardStart) * trimStart;
    sy = y1 + Math.sin(outwardStart) * trimStart;
    bx1 = sx + Math.cos(outwardStart) * ctrlLen;
    by1 = sy + Math.sin(outwardStart) * ctrlLen;
  }
  if (trimEnd > 0) {
    ex = x2 + Math.cos(outwardEnd) * trimEnd;
    ey = y2 + Math.sin(outwardEnd) * trimEnd;
    bx2 = ex + Math.cos(outwardEnd) * ctrlLen;
    by2 = ey + Math.sin(outwardEnd) * ctrlLen;
  }
  return `M ${sx} ${sy} C ${bx1} ${by1}, ${bx2} ${by2}, ${ex} ${ey}`;
}

function edgeInputArrowPolygon(ax, ay, outward) {
  const cos = Math.cos(outward);
  const sin = Math.sin(outward);
  const backX = ax + cos * WORKFLOW_ARROW_BACK;
  const backY = ay + sin * WORKFLOW_ARROW_BACK;
  return [
    `${ax},${ay}`,
    `${backX - sin * WORKFLOW_ARROW_HALF_W},${backY + cos * WORKFLOW_ARROW_HALF_W}`,
    `${backX + sin * WORKFLOW_ARROW_HALF_W},${backY - cos * WORKFLOW_ARROW_HALF_W}`,
  ].join(" ");
}

function edgeOutputCapSegment(ax, ay, outward) {
  const tangent = outward + Math.PI / 2;
  const cos = Math.cos(tangent);
  const sin = Math.sin(tangent);
  const half = WORKFLOW_OUTPUT_CAP_HALF;
  return {
    x1: ax - cos * half,
    y1: ay - sin * half,
    x2: ax + cos * half,
    y2: ay + sin * half,
  };
}

function scheduleWorkflowFrame() {
  if (workflowFrameQueued) return;
  workflowFrameQueued = true;
  requestAnimationFrame(() => {
    workflowFrameQueued = false;
    paintEdges();
  });
}

function ensureEdgeGraphics() {
  if (edgePathEls.length === EDGES.length && edgeCountLabelEls.length === EDGES.length) return;
  const svg = edgesSvg();
  const arrowLayer = arrowsSvg();
  if (!svg || !arrowLayer) return;
  edgePathEls = [];
  edgeOutCapEls = [];
  edgeInArrowEls = [];
  edgeCountLabelEls = [];
  svg.replaceChildren();
  arrowLayer.replaceChildren();
  const pathGroup = document.createElementNS(SVG_NS, "g");
  pathGroup.setAttribute("class", "workflow-edge-layer");
  const labelGroup = document.createElementNS(SVG_NS, "g");
  labelGroup.setAttribute("class", "workflow-edge-label-layer");
  const arrowGroup = document.createElementNS(SVG_NS, "g");
  arrowGroup.setAttribute("class", "workflow-edge-arrow-layer");
  for (let i = 0; i < EDGES.length; i++) {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", "workflow-edge");
    pathGroup.appendChild(path);
    edgePathEls.push(path);
    const label = document.createElementNS(SVG_NS, "text");
    label.setAttribute("class", "workflow-edge-count");
    labelGroup.appendChild(label);
    edgeCountLabelEls.push(label);
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("class", "workflow-edge-output-cap");
    const poly = document.createElementNS(SVG_NS, "polygon");
    poly.setAttribute("class", "workflow-edge-arrow workflow-edge-arrow--in");
    arrowGroup.appendChild(line);
    arrowGroup.appendChild(poly);
    edgeOutCapEls.push(line);
    edgeInArrowEls.push(poly);
  }
  svg.appendChild(pathGroup);
  svg.appendChild(labelGroup);
  arrowLayer.appendChild(arrowGroup);
}

function setEdgeSurfaceSize(w, h) {
  if (w === lastSurfaceW && h === lastSurfaceH) return;
  lastSurfaceW = w;
  lastSurfaceH = h;
  for (const surface of [edgesSvg(), arrowsSvg()]) {
    if (!surface) continue;
    surface.setAttribute("width", String(w));
    surface.setAttribute("height", String(h));
    surface.setAttribute("viewBox", `0 0 ${w} ${h}`);
  }
}

function repaintEdgeGraphics() {
  ensureEdgeGraphics();
  const layer = nodeLayer();
  const w = layer ? Number.parseFloat(layer.style.width) || MIN_CANVAS_W : MIN_CANVAS_W;
  const h = layer ? Number.parseFloat(layer.style.height) || MIN_CANVAS_H : MIN_CANVAS_H;
  setEdgeSurfaceSize(w, h);
  const fast = Boolean(dragState);
  for (const surface of [edgesSvg(), arrowsSvg()]) {
    surface?.setAttribute("shape-rendering", fast ? "optimizeSpeed" : "geometricPrecision");
  }
  const dragId = dragState?.id;
  for (let i = 0; i < EDGES.length; i++) {
    const edge = EDGES[i];
    if (dragId && edge.from !== dragId && edge.to !== dragId) continue;
    const from = socketPoint(edge.from, edge.fromSocket);
    const to = socketPoint(edge.to, edge.toSocket);
    const pathEl = edgePathEls[i];
    const capEl = edgeOutCapEls[i];
    const arrowEl = edgeInArrowEls[i];
    if (!from || !to || !pathEl || !capEl || !arrowEl) continue;
    const lane = edge.lane || 0;
    const outwardStart = anchorOutwardAngle(from.x, from.y, edge.from, from.x, from.y, to.x, to.y, lane, false);
    const outwardEnd = anchorOutwardAngle(to.x, to.y, edge.to, from.x, from.y, to.x, to.y, lane, true);
    pathEl.setAttribute(
      "d",
      edgePath(
        from.x,
        from.y,
        to.x,
        to.y,
        lane,
        WORKFLOW_OUTPUT_LINE_TRIM,
        WORKFLOW_ARROW_BACK,
        outwardStart,
        outwardEnd,
      ),
    );
    const outCap = edgeOutputCapSegment(from.x, from.y, outwardStart);
    capEl.setAttribute("x1", String(outCap.x1));
    capEl.setAttribute("y1", String(outCap.y1));
    capEl.setAttribute("x2", String(outCap.x2));
    capEl.setAttribute("y2", String(outCap.y2));
    arrowEl.setAttribute("points", edgeInputArrowPolygon(to.x, to.y, outwardEnd));
    const labelEl = edgeCountLabelEls[i];
    if (labelEl) {
      const mx = (from.x + to.x) / 2;
      const my = (from.y + to.y) / 2;
      const count = edgeLeadCount(edge.id);
      labelEl.setAttribute("x", String(mx));
      labelEl.setAttribute("y", String(my));
      labelEl.textContent = count > 0 ? String(count) : "";
    }
  }
}

function paintEdges() {
  if (!edgesSvg()) return;
  applyLayout();
  repaintEdgeGraphics();
}

function onWorkflowFlowUpdated() {
  loadFixedEdges();
  ensureEdgeGraphics();
  paintWorkflowNodeCounts();
  scheduleWorkflowFrame();
}

function refreshWorkflowCanvas() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  if (workflowViewportInteracting()) return;
  applyCamera();
  paintWorkflowNodeCounts();
  scheduleWorkflowFrame();
}

function dragEdgePanDelta(clientX, clientY, dtMs) {
  const rect = viewportRect();
  if (!rect || dtMs <= 0) return { dx: 0, dy: 0 };
  const dt = dtMs / 1000;
  const inset = DRAG_EDGE_INSET;
  const max = DRAG_EDGE_PAN_MAX;
  let vx = 0;
  let vy = 0;
  if (clientX < rect.left + inset) {
    vx = max * Math.min(1, (rect.left + inset - clientX) / inset);
  } else if (clientX > rect.right - inset) {
    vx = -max * Math.min(1, (clientX - (rect.right - inset)) / inset);
  }
  if (clientY < rect.top + inset) {
    vy = max * Math.min(1, (rect.top + inset - clientY) / inset);
  } else if (clientY > rect.bottom - inset) {
    vy = -max * Math.min(1, (clientY - (rect.bottom - inset)) / inset);
  }
  return { dx: vx * dt, dy: vy * dt };
}

function stopDragEdgeLoop() {
  if (dragEdgeFrame) cancelAnimationFrame(dragEdgeFrame);
  dragEdgeFrame = 0;
  if (dragState) dragState.lastFrameTs = 0;
}

function startDragEdgeLoop() {
  stopDragEdgeLoop();
  const tick = (now) => {
    if (!dragState) return;
    const prev = dragState.lastFrameTs || now;
    const dtMs = Math.min(32, Math.max(DRAG_EDGE_FRAME_MS, now - prev));
    dragState.lastFrameTs = now;
    const edgePan = dragEdgePanDelta(lastDragPointer.x, lastDragPointer.y, dtMs);
    if (edgePan.dx || edgePan.dy) {
      camera.panX += edgePan.dx;
      camera.panY += edgePan.dy;
      applyCamera();
    }
    dragEdgeFrame = requestAnimationFrame(tick);
  };
  dragEdgeFrame = requestAnimationFrame(tick);
}

function onPointerMove(event) {
  if (panState) {
    panState.latestX = event.clientX;
    panState.latestY = event.clientY;
    pushPanSample(panState.samples, event.clientX, event.clientY);
    schedulePanCameraApply();
    return;
  }
  if (!dragState) return;
  lastDragPointer.x = event.clientX;
  lastDragPointer.y = event.clientY;
  const pt = clientToWorld(event.clientX, event.clientY);
  layout[dragState.id] = {
    x: clampLogicalCoord(pt.x - dragState.offsetX),
    y: clampLogicalCoord(pt.y - dragState.offsetY),
  };
  scheduleWorkflowFrame();
}

function endInteraction(event) {
  if (panState) {
    applyPanCameraFromState();
    const samples = panState.samples;
    const releaseVelocity = panReleaseVelocity(samples);
    viewport()?.releasePointerCapture?.(panState.pointerId);
    panState = null;
    panCameraFrameQueued = false;
    viewport()?.classList.remove("is-panning");
    syncWorkflowInteractionClass();
    if (releaseVelocity.vx || releaseVelocity.vy) startPanInertia(releaseVelocity.vx, releaseVelocity.vy);
    else saveCamera();
  }
  if (dragState) {
    stopDragEdgeLoop();
    dragState.node.classList.remove("is-dragging");
    dragState = null;
    syncWorkflowInteractionClass();
    paintEdges();
    saveLayout();
    saveCamera();
  }
  document.removeEventListener("pointermove", onPointerMove);
  document.removeEventListener("pointerup", endInteraction);
  document.removeEventListener("pointercancel", endInteraction);
}

function pointerStartsCanvasPan(event) {
  if (event.button === 1) return true;
  if (event.button !== 0 || panState || dragState) return false;
  if (workflowToolBlocksNodeDrag()) return false;
  if (event.target.closest(".workflow-node-header")) return false;
  if (event.target.closest(".workflow-node-info-btn, .workflow-resize-handle, .workflow-socket")) return false;
  if (event.target.closest("button, a, input, select, textarea, label, [contenteditable='true']")) return false;
  return true;
}

function zoomCameraAtClient(clientX, clientY, deltaY, { pinch = false } = {}) {
  const view = viewport();
  if (!view) return;
  const rect = view.getBoundingClientRect();
  const px = clientX - rect.left;
  const py = clientY - rect.top;
  const displayX = (px - camera.panX) / camera.scale;
  const displayY = (py - camera.panY) / camera.scale;
  const intensity = pinch ? TRACKPAD_ZOOM_INTENSITY : ZOOM_INTENSITY;
  const factor = Math.exp(-deltaY * intensity);
  const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, camera.scale * factor));
  camera.scale = nextScale;
  camera.panX = px - displayX * nextScale;
  camera.panY = py - displayY * nextScale;
  applyCamera();
  saveCamera();
}

/** Mouse wheel (incl. middle detent) should zoom; two-finger trackpad scroll should pan. */
function isMouseWheelEvent(event) {
  if (event.deltaMode === WHEEL_DELTA_LINE) return true;
  const legacyDelta = event.wheelDelta;
  if (legacyDelta && Math.abs(legacyDelta) % 120 === 0) return true;
  if (event.deltaMode === WHEEL_DELTA_PIXEL) {
    const absY = Math.abs(event.deltaY);
    const absX = Math.abs(event.deltaX);
    if (absX < 0.5 && absY >= 48) return true;
  }
  return false;
}

function wheelPansViewport(event) {
  if (event.ctrlKey || event.metaKey) return false;
  if (event.buttons & 4) return false;
  if (panState) return false;
  if (isMouseWheelEvent(event)) return false;
  if (event.deltaX !== 0) return true;
  if (event.deltaMode !== WHEEL_DELTA_PIXEL) return false;
  return event.deltaY !== 0;
}

function wheelDeltaToPx(deltaX, deltaY, deltaMode) {
  if (deltaMode === WHEEL_DELTA_LINE) {
    return { dx: deltaX * WHEEL_LINE_TO_PX, dy: deltaY * WHEEL_LINE_TO_PX };
  }
  return { dx: deltaX, dy: deltaY };
}

function flushWheelPan() {
  wheelPanRaf = 0;
  const { dx, dy } = wheelPanAccum;
  wheelPanAccum.dx = 0;
  wheelPanAccum.dy = 0;
  if (!dx && !dy) return;
  camera.panX -= dx;
  camera.panY -= dy;
  applyCamera();
  saveCamera();
}

function queueWheelPan(deltaX, deltaY, deltaMode) {
  const { dx, dy } = wheelDeltaToPx(deltaX, deltaY, deltaMode);
  wheelPanAccum.dx += dx;
  wheelPanAccum.dy += dy;
  if (wheelPanRaf) return;
  wheelPanRaf = requestAnimationFrame(flushWheelPan);
}

function startPan(event) {
  if (!pointerStartsCanvasPan(event)) return;
  event.preventDefault();
  stopPanInertia();
  const samples = [];
  pushPanSample(samples, event.clientX, event.clientY);
  panState = {
    originX: event.clientX,
    originY: event.clientY,
    latestX: event.clientX,
    latestY: event.clientY,
    originPanX: camera.panX,
    originPanY: camera.panY,
    pointerId: event.pointerId,
    samples,
  };
  viewport()?.classList.add("is-panning");
  syncWorkflowInteractionClass();
  viewport()?.setPointerCapture?.(event.pointerId);
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", endInteraction);
  document.addEventListener("pointercancel", endInteraction);
}

function startDrag(event) {
  if (event.button !== 0 || panState) return;
  if (workflowToolBlocksNodeDrag()) return;
  if (event.target.closest(".workflow-node-info-btn")) return;
  stopPanInertia();
  const header = event.target.closest(".workflow-node-header");
  if (!header) return;
  const node = header.closest("[data-workflow-node]");
  if (!node) return;
  event.preventDefault();
  const id = node.dataset.workflowNode;
  const pos = layout[id] || { x: 0, y: 0 };
  const pt = clientToWorld(event.clientX, event.clientY);
  dragState = {
    id,
    node,
    offsetX: pt.x - pos.x,
    offsetY: pt.y - pos.y,
    frozenOrigin: { ...canvasOrigin },
    lastFrameTs: 0,
  };
  lastDragPointer.x = event.clientX;
  lastDragPointer.y = event.clientY;
  layout[id] = { x: pos.x, y: pos.y };
  node.classList.add("is-dragging");
  syncWorkflowInteractionClass();
  startDragEdgeLoop();
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", endInteraction);
  document.addEventListener("pointercancel", endInteraction);
}

function onWheel(event) {
  const view = viewport();
  if (!view || view !== event.currentTarget) return;
  event.preventDefault();
  stopPanInertia();
  if (wheelPansViewport(event)) {
    queueWheelPan(event.deltaX, event.deltaY, event.deltaMode);
    return;
  }
  const pinch = event.ctrlKey || event.metaKey;
  zoomCameraAtClient(event.clientX, event.clientY, event.deltaY, { pinch });
}

function suppressMiddleAutoScroll(event) {
  if (event.button === 1) event.preventDefault();
}

export function repaintWorkflowEdges() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  scheduleWorkflowFrame();
}

export function bindWorkflow() {
  if (bound) return;
  bound = true;
  loadLayout();
  loadSocketLayout();
  mountWorkflowInstances(nodeLayer());
  applyCamera();
  applyLayout();
  bindWorkflowTools({
    onAnchorMoved: scheduleWorkflowFrame,
    onResizeComplete: ({ nodeId, w, h, paintingOnly } = {}) => {
      if (w && h && nodeId) updateInstanceSize(nodeId, w, h);
      if (!paintingOnly) saveWorkflowInstances();
      scheduleWorkflowFrame();
    },
  });
  bindWorkflowCrmSidebar();
  bindCampaignChrome();
  bindCampaignFlow();
  bindCampaignImportDialog();
  bindWorkflowConnections({
    getSocketLayerPoint: socketPoint,
    layerPointFromClient,
    buildWirePathD,
    tryAddEdge: tryAddWorkflowEdge,
    listEdges: () => EDGES,
    onWireFrame: scheduleWorkflowFrame,
  });
  const layer = nodeLayer();
  const view = viewport();
  layer?.addEventListener("pointerdown", startDrag);
  view?.addEventListener("pointerdown", startPan);
  view?.addEventListener("wheel", onWheel, { passive: false });
  view?.addEventListener("auxclick", suppressMiddleAutoScroll);
  view?.addEventListener("contextmenu", (event) => event.preventDefault());
  window.addEventListener("godial-workflow-relayout", () => repaintWorkflowEdges());
  window.addEventListener("godial-workflow-flow", onWorkflowFlowUpdated);
  window.addEventListener("resize", refreshWorkflowCanvas);
  registerRenderer(refreshWorkflowCanvas, "end", "workflow");
}

export function initWorkflowTab() {
  refreshWorkflowCanvas();
  releaseWorkflowCrmSidebarDom();
  renderWorkflowCrmSidebar();
  void refreshCampaignCatalog().then(() => refreshCampaignFlow());
}