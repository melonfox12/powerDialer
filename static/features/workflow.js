import { registerRenderer } from "../core.js";
import { bindOfficeAgents, renderOfficeAgents } from "./_workflow/office-agents.js";
import {
  applySocketLayouts,
  bindWorkflowTools,
  loadSocketLayout,
  socketCenterOnNode,
  workflowToolBlocksNodeDrag,
} from "./_workflow/tools.js";

const LAYOUT_KEY = "godial-workflow-layout";
const CAMERA_KEY = "godial-workflow-camera";
const MIN_CANVAS_W = 2280;
const MIN_CANVAS_H = 920;
const MAX_SPAN_W = 24000;
const MAX_SPAN_H = 16000;
const LOGICAL_COORD_LIMIT = 30000;
const CANVAS_PAD = 180;
const ZOOM_INTENSITY = 0.00115;
const MIN_SCALE = 0.22;
const MAX_SCALE = 2.75;
const PAN_VELOCITY_WINDOW_MS = 110;
const PAN_RELEASE_GAIN = 0.78;
const PAN_MAX_SPEED = 2.05;
const PAN_MIN_SPEED = 0.09;
const PAN_DECAY_PER_SEC = 5.4;

const EDGES = [
  { from: "prospect-list", fromSocket: "out", to: "phone-lookup", toSocket: "in" },
  { from: "phone-lookup", fromSocket: "out", to: "format-org", toSocket: "in" },
  { from: "format-org", fromSocket: "out", to: "caller-pool", toSocket: "in" },
  { from: "caller-pool", fromSocket: "out", to: "digital-office", toSocket: "in" },
  { from: "digital-office", fromSocket: "out-sync", to: "organizer", toSocket: "in-b", hub: true, lane: 1 },
  { from: "organizer", fromSocket: "out-b", to: "digital-office", toSocket: "in-sync", hub: true, lane: -1 },
  { from: "pipeline", fromSocket: "out-sync", to: "organizer", toSocket: "in-a", hub: true, lane: 1 },
  { from: "organizer", fromSocket: "out-a", to: "pipeline", toSocket: "in-sync", hub: true, lane: -1 },
];

const DEFAULT_LAYOUT = {
  "prospect-list": { x: 48, y: 140 },
  "phone-lookup": { x: 340, y: 100 },
  "format-org": { x: 700, y: 100 },
  "caller-pool": { x: 1020, y: 140 },
  "digital-office": { x: 1180, y: 300 },
  organizer: { x: 1580, y: 280 },
  pipeline: { x: 1980, y: 300 },
};

const DEFAULT_CAMERA = { panX: 24, panY: 20, scale: 0.92 };

let layout = { ...DEFAULT_LAYOUT };
let camera = { ...DEFAULT_CAMERA };
let dragState = null;
let panState = null;
let panInertia = null;
let panInertiaFrame = 0;
let bound = false;
/** Top-left of the scrollable workspace in logical coordinates (can be negative). */
let canvasOrigin = { x: 0, y: 0 };

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

function loadLayout() {
  try {
    const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}");
    layout = { ...DEFAULT_LAYOUT, ...saved };
  } catch {
    layout = { ...DEFAULT_LAYOUT };
  }
  try {
    const savedCam = JSON.parse(localStorage.getItem(CAMERA_KEY) || "{}");
    camera = { ...DEFAULT_CAMERA, ...savedCam };
    camera.scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, camera.scale));
  } catch {
    camera = { ...DEFAULT_CAMERA };
  }
}

function saveLayout() {
  try {
    localStorage.setItem(LAYOUT_KEY, JSON.stringify(layout));
  } catch {
    // ignore quota
  }
}

function saveCamera() {
  try {
    localStorage.setItem(CAMERA_KEY, JSON.stringify(camera));
  } catch {
    // ignore quota
  }
}

function defaultNodeSize(node) {
  if (node?.classList.contains("workflow-node--group")) return { w: 360, h: 420 };
  if (node?.classList.contains("workflow-node--organizer")) return { w: 320, h: 300 };
  if (node?.classList.contains("workflow-node--pipeline")) return { w: 300, h: 220 };
  return { w: 268, h: 160 };
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
    const pos = layout[id] || DEFAULT_LAYOUT[id];
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
  const { minX, minY, maxX, maxY } = measureContentBounds();
  canvasOrigin = { x: minX, y: minY };
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
  el.style.transform = `translate(${camera.panX}px, ${camera.panY}px) scale(${camera.scale})`;
  const layer = nodeLayer();
  const svg = edgesSvg();
  const arrowLayer = arrowsSvg();
  if (layer) layer.style.transform = "";
  if (svg) svg.style.transform = "";
  if (arrowLayer) arrowLayer.style.transform = "";
}

function stopPanInertia() {
  if (panInertiaFrame) cancelAnimationFrame(panInertiaFrame);
  panInertiaFrame = 0;
  panInertia = null;
  viewport()?.classList.remove("is-gliding");
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
    paintEdges();
    if (Math.hypot(panInertia.vx, panInertia.vy) < PAN_MIN_SPEED) {
      stopPanInertia();
      saveCamera();
      return;
    }
    panInertiaFrame = requestAnimationFrame(tick);
  };
  panInertiaFrame = requestAnimationFrame(tick);
}

function applyLayout() {
  const layer = nodeLayer();
  if (!layer) return;
  updateWorkspaceBounds();
  for (const node of layer.querySelectorAll("[data-workflow-node]")) {
    const id = node.dataset.workflowNode;
    const pos = layout[id] || DEFAULT_LAYOUT[id];
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

  const pos = layout[nodeId] || DEFAULT_LAYOUT[nodeId];
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
  const pos = layout[nodeId] || DEFAULT_LAYOUT[nodeId];
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

function edgePath(x1, y1, x2, y2, lane = 0, trimStart = 0, trimEnd = 0, fromNodeId = "", toNodeId = "") {
  const { bx1, by1, bx2, by2 } = edgeBezierControls(x1, y1, x2, y2, lane);
  let sx = x1;
  let sy = y1;
  let ex = x2;
  let ey = y2;
  if (trimStart > 0) {
    const outward =
      edgeOutwardFromNodeCenter(x1, y1, fromNodeId) ?? edgeTangentAngleAtStart(x1, y1, x2, y2, lane);
    sx = x1 + Math.cos(outward) * trimStart;
    sy = y1 + Math.sin(outward) * trimStart;
  }
  if (trimEnd > 0) {
    const outward = edgeOutwardFromNodeCenter(x2, y2, toNodeId) ?? edgeTangentAngleAtEnd(x1, y1, x2, y2, lane);
    ex = x2 + Math.cos(outward) * trimEnd;
    ey = y2 + Math.sin(outward) * trimEnd;
  }
  return `M ${sx} ${sy} C ${bx1} ${by1}, ${bx2} ${by2}, ${ex} ${ey}`;
}

function edgeInputArrowPoints(x1, y1, x2, y2, lane, toNodeId, ax, ay) {
  const outward =
    edgeOutwardFromNodeCenter(ax, ay, toNodeId) ?? edgeTangentAngleAtEnd(x1, y1, x2, y2, lane);
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

/** Output anchor — tip points along the edge, away from the source node block. */
function edgeOutputArrowPoints(x1, y1, x2, y2, lane, fromNodeId, ax, ay) {
  const outward =
    edgeOutwardFromNodeCenter(ax, ay, fromNodeId) ?? edgeTangentAngleAtStart(x1, y1, x2, y2, lane);
  const cos = Math.cos(outward);
  const sin = Math.sin(outward);
  const backX = ax - cos * WORKFLOW_ARROW_BACK;
  const backY = ay - sin * WORKFLOW_ARROW_BACK;
  return [
    `${ax},${ay}`,
    `${backX - sin * WORKFLOW_ARROW_HALF_W},${backY + cos * WORKFLOW_ARROW_HALF_W}`,
    `${backX + sin * WORKFLOW_ARROW_HALF_W},${backY - cos * WORKFLOW_ARROW_HALF_W}`,
  ].join(" ");
}

function paintEdges() {
  const svg = edgesSvg();
  const arrowLayer = arrowsSvg();
  if (!svg) return;
  applyLayout();
  const layer = nodeLayer();
  const w = layer ? Number.parseFloat(layer.style.width) || MIN_CANVAS_W : MIN_CANVAS_W;
  const h = layer ? Number.parseFloat(layer.style.height) || MIN_CANVAS_H : MIN_CANVAS_H;
  for (const surface of [svg, arrowLayer]) {
    if (!surface) continue;
    surface.setAttribute("width", String(w));
    surface.setAttribute("height", String(h));
    surface.setAttribute("viewBox", `0 0 ${w} ${h}`);
    surface.setAttribute("shape-rendering", "geometricPrecision");
  }
  const paths = ['<g class="workflow-edge-layer">'];
  const arrows = ['<g class="workflow-edge-arrow-layer">'];
  for (const edge of EDGES) {
    const from = socketPoint(edge.from, edge.fromSocket);
    const to = socketPoint(edge.to, edge.toSocket);
    if (!from || !to) continue;
    const lane = edge.lane || 0;
    const trim = WORKFLOW_ARROW_BACK;
    const path = edgePath(from.x, from.y, to.x, to.y, lane, trim, trim, edge.from, edge.to);
    paths.push(`<path class="workflow-edge" d="${path}" />`);
    arrows.push(
      `<polygon class="workflow-edge-arrow workflow-edge-arrow--out" points="${edgeOutputArrowPoints(from.x, from.y, to.x, to.y, lane, edge.from, from.x, from.y)}" />`,
    );
    arrows.push(
      `<polygon class="workflow-edge-arrow workflow-edge-arrow--in" points="${edgeInputArrowPoints(from.x, from.y, to.x, to.y, lane, edge.to, to.x, to.y)}" />`,
    );
  }
  paths.push("</g>");
  arrows.push("</g>");
  svg.innerHTML = paths.join("");
  if (arrowLayer) arrowLayer.innerHTML = arrows.join("");
}

function refreshWorkflowCanvas() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  applyCamera();
  requestAnimationFrame(paintEdges);
}

function onPointerMove(event) {
  if (panState) {
    camera.panX = panState.originPanX + (event.clientX - panState.originX);
    camera.panY = panState.originPanY + (event.clientY - panState.originY);
    pushPanSample(panState.samples, event.clientX, event.clientY);
    applyCamera();
    paintEdges();
    return;
  }
  if (!dragState) return;
  const pt = clientToWorld(event.clientX, event.clientY);
  layout[dragState.id] = {
    x: clampLogicalCoord(pt.x - dragState.offsetX),
    y: clampLogicalCoord(pt.y - dragState.offsetY),
  };
  paintEdges();
}

function endInteraction(event) {
  if (panState) {
    const samples = panState.samples;
    const releaseVelocity = panReleaseVelocity(samples);
    viewport()?.releasePointerCapture?.(panState.pointerId);
    panState = null;
    viewport()?.classList.remove("is-panning");
    if (releaseVelocity.vx || releaseVelocity.vy) startPanInertia(releaseVelocity.vx, releaseVelocity.vy);
    else saveCamera();
  }
  if (dragState) {
    dragState.node.classList.remove("is-dragging");
    dragState = null;
    saveLayout();
  }
  document.removeEventListener("pointermove", onPointerMove);
  document.removeEventListener("pointerup", endInteraction);
  document.removeEventListener("pointercancel", endInteraction);
}

function startPan(event) {
  if (event.button !== 1) return;
  event.preventDefault();
  stopPanInertia();
  const samples = [];
  pushPanSample(samples, event.clientX, event.clientY);
  panState = {
    originX: event.clientX,
    originY: event.clientY,
    originPanX: camera.panX,
    originPanY: camera.panY,
    pointerId: event.pointerId,
    samples,
  };
  viewport()?.classList.add("is-panning");
  viewport()?.setPointerCapture?.(event.pointerId);
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", endInteraction);
  document.addEventListener("pointercancel", endInteraction);
}

function startDrag(event) {
  if (event.button !== 0 || panState) return;
  if (workflowToolBlocksNodeDrag()) return;
  stopPanInertia();
  const header = event.target.closest(".workflow-node-header");
  if (!header) return;
  const node = header.closest("[data-workflow-node]");
  if (!node) return;
  event.preventDefault();
  const id = node.dataset.workflowNode;
  const pos = layout[id] || DEFAULT_LAYOUT[id] || { x: 0, y: 0 };
  const pt = clientToWorld(event.clientX, event.clientY);
  dragState = {
    id,
    node,
    offsetX: pt.x - pos.x,
    offsetY: pt.y - pos.y,
  };
  layout[id] = { x: pos.x, y: pos.y };
  node.classList.add("is-dragging");
  document.addEventListener("pointermove", onPointerMove);
  document.addEventListener("pointerup", endInteraction);
  document.addEventListener("pointercancel", endInteraction);
}

function onWheel(event) {
  const view = viewport();
  if (!view || view !== event.currentTarget) return;
  event.preventDefault();
  stopPanInertia();
  const rect = view.getBoundingClientRect();
  const px = event.clientX - rect.left;
  const py = event.clientY - rect.top;
  const displayX = (px - camera.panX) / camera.scale;
  const displayY = (py - camera.panY) / camera.scale;
  const factor = Math.exp(-event.deltaY * ZOOM_INTENSITY);
  const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, camera.scale * factor));
  camera.scale = nextScale;
  camera.panX = px - displayX * nextScale;
  camera.panY = py - displayY * nextScale;
  applyCamera();
  paintEdges();
  saveCamera();
}

function suppressMiddleAutoScroll(event) {
  if (event.button === 1) event.preventDefault();
}

export function repaintWorkflowEdges() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  requestAnimationFrame(paintEdges);
}

export function bindWorkflow() {
  if (bound) return;
  bound = true;
  loadLayout();
  loadSocketLayout();
  applyCamera();
  applyLayout();
  bindWorkflowTools({ onAnchorMoved: paintEdges });
  const layer = nodeLayer();
  const view = viewport();
  layer?.addEventListener("pointerdown", startDrag);
  view?.addEventListener("pointerdown", startPan);
  view?.addEventListener("wheel", onWheel, { passive: false });
  view?.addEventListener("auxclick", suppressMiddleAutoScroll);
  view?.addEventListener("contextmenu", (event) => event.preventDefault());
  bindOfficeAgents();
  window.addEventListener("godial-workflow-relayout", () => repaintWorkflowEdges());
  window.addEventListener("resize", refreshWorkflowCanvas);
  registerRenderer(refreshWorkflowCanvas, "end", "workflow");
}

export function initWorkflowTab() {
  renderOfficeAgents();
  refreshWorkflowCanvas();
}