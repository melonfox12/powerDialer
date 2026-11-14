import { registerRenderer } from "../core.js";

const LAYOUT_KEY = "godial-workflow-layout";
const CAMERA_KEY = "godial-workflow-camera";
const CANVAS_W = 2280;
const CANVAS_H = 920;
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
  { from: "digital-office", fromSocket: "out-sync", to: "pipeline", toSocket: "in-sync", lane: 1 },
  { from: "pipeline", fromSocket: "out-sync", to: "digital-office", toSocket: "in-sync", lane: -1 },
];

const DEFAULT_LAYOUT = {
  "prospect-list": { x: 48, y: 140 },
  "phone-lookup": { x: 340, y: 100 },
  "format-org": { x: 700, y: 100 },
  "caller-pool": { x: 1020, y: 140 },
  "digital-office": { x: 1280, y: 320 },
  pipeline: { x: 1680, y: 300 },
};

const DEFAULT_CAMERA = { panX: 24, panY: 20, scale: 0.92 };

let layout = { ...DEFAULT_LAYOUT };
let camera = { ...DEFAULT_CAMERA };
let dragState = null;
let panState = null;
let panInertia = null;
let panInertiaFrame = 0;
let bound = false;

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

function applyCamera() {
  const el = world();
  if (!el) return;
  el.style.transform = `translate(${camera.panX}px, ${camera.panY}px) scale(${camera.scale})`;
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
  for (const node of layer.querySelectorAll("[data-workflow-node]")) {
    const id = node.dataset.workflowNode;
    const pos = layout[id] || DEFAULT_LAYOUT[id];
    if (!pos) continue;
    node.style.left = `${pos.x}px`;
    node.style.top = `${pos.y}px`;
  }
}

function viewportRect() {
  return viewport()?.getBoundingClientRect();
}

function clientToWorld(clientX, clientY) {
  const rect = viewportRect();
  if (!rect) return { x: 0, y: 0 };
  return {
    x: (clientX - rect.left - camera.panX) / camera.scale,
    y: (clientY - rect.top - camera.panY) / camera.scale,
  };
}

function socketPoint(nodeId, socketName) {
  const layer = nodeLayer();
  if (!layer) return null;
  const node = layer.querySelector(`[data-workflow-node="${nodeId}"]`);
  if (!node) return null;
  const socket = node.querySelector(`[data-socket="${socketName}"]`);
  if (!socket) return null;

  const nodeLeft = Number.parseFloat(node.style.left) || layout[nodeId]?.x || 0;
  const nodeTop = Number.parseFloat(node.style.top) || layout[nodeId]?.y || 0;
  const nodeRect = node.getBoundingClientRect();
  const socketRect = socket.getBoundingClientRect();
  const centerScreenX = socketRect.left + socketRect.width / 2;
  const centerScreenY = socketRect.top + socketRect.height / 2;
  const nodeScreenX = nodeRect.left;
  const nodeScreenY = nodeRect.top;
  const offsetX = (centerScreenX - nodeScreenX) / camera.scale;
  const offsetY = (centerScreenY - nodeScreenY) / camera.scale;

  return {
    x: nodeLeft + offsetX,
    y: nodeTop + offsetY,
  };
}

function edgePath(x1, y1, x2, y2, lane = 0) {
  const horizontal = Math.max(64, Math.abs(x2 - x1) * 0.48);
  const bend = lane * 16;
  return `M ${x1} ${y1} C ${x1 + horizontal} ${y1 + bend}, ${x2 - horizontal} ${y2 + bend}, ${x2} ${y2}`;
}

function syncArrowPoints(x1, y1, x2, y2, lane) {
  const t = 0.62;
  const horizontal = Math.max(64, Math.abs(x2 - x1) * 0.48);
  const bend = lane * 16;
  const bx1 = x1 + horizontal;
  const bx2 = x2 - horizontal;
  const cx = Math.pow(1 - t, 3) * x1 + 3 * Math.pow(1 - t, 2) * t * bx1 + 3 * (1 - t) * t * t * bx2 + Math.pow(t, 3) * x2;
  const cy = Math.pow(1 - t, 3) * y1 + 3 * Math.pow(1 - t, 2) * t * (y1 + bend) + 3 * (1 - t) * t * t * (y2 + bend) + Math.pow(t, 3) * y2;
  const angle = Math.atan2(y2 - cy, x2 - cx);
  const tip = 9;
  const wing = 5;
  return [
    `${x2},${y2}`,
    `${x2 - Math.cos(angle) * tip - Math.sin(angle) * wing},${y2 - Math.sin(angle) * tip + Math.cos(angle) * wing}`,
    `${x2 - Math.cos(angle) * tip + Math.sin(angle) * wing},${y2 - Math.sin(angle) * tip - Math.cos(angle) * wing}`,
  ].join(" ");
}

function paintEdges() {
  const svg = edgesSvg();
  if (!svg) return;
  svg.setAttribute("width", String(CANVAS_W));
  svg.setAttribute("height", String(CANVAS_H));
  svg.setAttribute("viewBox", `0 0 ${CANVAS_W} ${CANVAS_H}`);
  const parts = ['<g class="workflow-edge-layer">'];
  for (const edge of EDGES) {
    const from = socketPoint(edge.from, edge.fromSocket);
    const to = socketPoint(edge.to, edge.toSocket);
    if (!from || !to) continue;
    const sync = edge.fromSocket.includes("sync");
    const lane = edge.lane || 0;
    const path = edgePath(from.x, from.y, to.x, to.y, lane);
    parts.push(`<path class="workflow-edge${sync ? " workflow-edge--sync" : ""}" d="${path}" />`);
    const capClass = sync ? "workflow-edge-cap workflow-edge-cap--sync" : "workflow-edge-cap";
    parts.push(`<circle class="${capClass}" cx="${from.x}" cy="${from.y}" r="4.5" />`);
    parts.push(`<circle class="${capClass}" cx="${to.x}" cy="${to.y}" r="4.5" />`);
    if (sync) {
      parts.push(`<polygon class="workflow-edge-arrow" points="${syncArrowPoints(from.x, from.y, to.x, to.y, lane)}" />`);
    }
  }
  parts.push("</g>");
  svg.innerHTML = parts.join("");
}

function refreshWorkflowCanvas() {
  if (document.getElementById("workflowTabPanel")?.hidden) return;
  applyCamera();
  applyLayout();
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
  const x = Math.max(0, Math.min(CANVAS_W - 40, pt.x - dragState.offsetX));
  const y = Math.max(0, Math.min(CANVAS_H - 40, pt.y - dragState.offsetY));
  dragState.node.style.left = `${x}px`;
  dragState.node.style.top = `${y}px`;
  layout[dragState.id] = { x, y };
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
  stopPanInertia();
  const header = event.target.closest(".workflow-node-header");
  if (!header) return;
  const node = header.closest("[data-workflow-node]");
  if (!node) return;
  event.preventDefault();
  const id = node.dataset.workflowNode;
  const left = Number.parseFloat(node.style.left) || layout[id]?.x || 0;
  const top = Number.parseFloat(node.style.top) || layout[id]?.y || 0;
  const pt = clientToWorld(event.clientX, event.clientY);
  dragState = {
    id,
    node,
    offsetX: pt.x - left,
    offsetY: pt.y - top,
  };
  layout[id] = { x: left, y: top };
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
  const worldX = (px - camera.panX) / camera.scale;
  const worldY = (py - camera.panY) / camera.scale;
  const factor = Math.exp(-event.deltaY * ZOOM_INTENSITY);
  const nextScale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, camera.scale * factor));
  camera.scale = nextScale;
  camera.panX = px - worldX * nextScale;
  camera.panY = py - worldY * nextScale;
  applyCamera();
  paintEdges();
  saveCamera();
}

function suppressMiddleAutoScroll(event) {
  if (event.button === 1) event.preventDefault();
}

function openAgentDialog(name) {
  const dialog = document.getElementById("workflowAgentSettingsDialog");
  const title = document.getElementById("workflowAgentDialogTitle");
  const nameInput = document.getElementById("workflowAgentDialogName");
  if (!dialog) return;
  if (title) title.textContent = `${name} — desk settings`;
  if (nameInput) nameInput.value = name;
  if (typeof dialog.showModal === "function") dialog.showModal();
}

export function bindWorkflow() {
  if (bound) return;
  bound = true;
  loadLayout();
  applyCamera();
  applyLayout();
  const layer = nodeLayer();
  const view = viewport();
  layer?.addEventListener("pointerdown", startDrag);
  view?.addEventListener("pointerdown", startPan);
  view?.addEventListener("wheel", onWheel, { passive: false });
  view?.addEventListener("auxclick", suppressMiddleAutoScroll);
  view?.addEventListener("contextmenu", (event) => event.preventDefault());
  for (const button of document.querySelectorAll(".workflow-agent-expand")) {
    button.addEventListener("click", () => openAgentDialog(button.dataset.agentName || "Agent"));
  }
  const dialog = document.getElementById("workflowAgentSettingsDialog");
  dialog?.addEventListener("click", (event) => {
    if (event.target === dialog) dialog.close();
  });
  window.addEventListener("resize", refreshWorkflowCanvas);
  registerRenderer(refreshWorkflowCanvas, "end", "workflow");
}

export function initWorkflowTab() {
  refreshWorkflowCanvas();
}