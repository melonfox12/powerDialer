const SOCKET_LAYOUT_KEY = "godial-workflow-socket-layout";

const SOCKET_DEFAULT_Y = {
  in: 0.5,
  out: 0.5,
  "in-sync": 0.38,
  "out-sync": 0.62,
  "in-a": 0.3,
  "in-b": 0.7,
  "out-a": 0.3,
  "out-b": 0.7,
};

let workflowTool = "pan";
let resizeState = null;
let onResizeComplete = () => {};
const MIN_NODE_W = 200;
const MIN_NODE_H = 120;
const MAX_NODE_W = 900;
const MAX_NODE_H = 720;
/** @type {Record<string, { t?: number, y?: number }>} */
let socketLayout = {};
let anchorDrag = null;
let toolsBound = false;
let onAnchorMoved = () => {};

function isInputSocket(name) {
  return name === "in" || name.startsWith("in-");
}

export function isWorkflowInputSocket(name) {
  return isInputSocket(name);
}

export function isWorkflowOutputSocket(name) {
  return name === "out" || name.startsWith("out-");
}

export function getWorkflowTool() {
  return workflowTool;
}

function perimeterLength(w, h) {
  return 2 * (w + h);
}

function tToPoint(t, w, h) {
  const perim = perimeterLength(w, h);
  let s = ((t % 1) + 1) % 1 * perim;
  if (s < w) return { x: s, y: 0 };
  s -= w;
  if (s < h) return { x: w, y: s };
  s -= h;
  if (s < w) return { x: w - s, y: h };
  s -= w;
  return { x: 0, y: h - s };
}

function pointToT(x, y, w, h) {
  const perim = perimeterLength(w, h);
  const eps = 0.75;
  if (y <= eps) return Math.max(0, Math.min(w, x)) / perim;
  if (x >= w - eps) return (w + Math.max(0, Math.min(h, y))) / perim;
  if (y >= h - eps) return (w + h + Math.max(0, Math.min(w, w - x))) / perim;
  if (x <= eps) return (2 * w + h + Math.max(0, Math.min(h, h - y))) / perim;
  return (2 * w + h + h * 0.5) / perim;
}

function projectToSegment(px, py, x1, y1, x2, y2) {
  const dx = x2 - x1;
  const dy = y2 - y1;
  const len2 = dx * dx + dy * dy;
  let u = len2 ? ((px - x1) * dx + (py - y1) * dy) / len2 : 0;
  u = Math.max(0, Math.min(1, u));
  return { x: x1 + u * dx, y: y1 + u * dy };
}

function closestPointOnPerimeter(px, py, w, h) {
  const top = projectToSegment(px, py, 0, 0, w, 0);
  const right = projectToSegment(px, py, w, 0, w, h);
  const bottom = projectToSegment(px, py, w, h, 0, h);
  const left = projectToSegment(px, py, 0, h, 0, 0);
  const candidates = [top, right, bottom, left];
  let best = top;
  let bestD = Infinity;
  for (const c of candidates) {
    const d = (c.x - px) ** 2 + (c.y - py) ** 2;
    if (d < bestD) {
      bestD = d;
      best = c;
    }
  }
  return { ...best, t: pointToT(best.x, best.y, w, h) };
}

function socketTransform(x, y, w, h) {
  const eps = Math.min(w, h) * 0.02;
  const onLeft = x <= eps;
  const onRight = x >= w - eps;
  const onTop = y <= eps;
  const onBottom = y >= h - eps;
  let tx = 0;
  let ty = -50;
  if (onLeft) tx = -50;
  else if (onRight) tx = 50;
  if (onBottom) ty = 50;
  else if (onTop) ty = -50;
  return `translate(${tx}%, ${ty}%)`;
}

function positionSocketElement(socket, t, w, h) {
  const { x, y } = tToPoint(t, w, h);
  socket.style.left = `${(x / w) * 100}%`;
  socket.style.top = `${(y / h) * 100}%`;
  socket.style.right = "auto";
  socket.style.bottom = "auto";
  socket.style.transform = socketTransform(x, y, w, h);
}

function defaultSocketT(socketName, w, h) {
  const y = SOCKET_DEFAULT_Y[socketName] ?? 0.5;
  const onLeft = isInputSocket(socketName);
  const x = onLeft ? 0 : w;
  const py = y * h;
  return pointToT(x, py, w, h);
}

function resolveSocketT(nodeId, socketName, w, h) {
  const key = socketKey(nodeId, socketName);
  const entry = socketLayout[key];
  if (entry?.t != null && Number.isFinite(entry.t)) {
    return entry.t;
  }
  if (entry?.y != null && Number.isFinite(entry.y)) {
    const onLeft = isInputSocket(socketName);
    const x = onLeft ? 0 : w;
    return pointToT(x, entry.y * h, w, h);
  }
  return defaultSocketT(socketName, w, h);
}

export function loadSocketLayout() {
  try {
    socketLayout = JSON.parse(localStorage.getItem(SOCKET_LAYOUT_KEY) || "{}");
  } catch {
    socketLayout = {};
  }
}

function saveSocketLayout() {
  try {
    localStorage.setItem(SOCKET_LAYOUT_KEY, JSON.stringify(socketLayout));
  } catch {
  }
}

function socketKey(nodeId, socketName) {
  return `${nodeId}:${socketName}`;
}

/** Anchor center in node-local pixels (matches perimeter `t`, not layout-thrashy DOM reads). */
export function socketCenterOnNode(nodeId, socketName, node) {
  const w = node.offsetWidth;
  const h = node.offsetHeight;
  if (!w || !h) return null;
  const t = resolveSocketT(nodeId, socketName, w, h);
  return tToPoint(t, w, h);
}

export function applySocketLayouts() {
  const layer = document.getElementById("workflowNodeLayer");
  if (!layer) return;
  for (const node of layer.querySelectorAll("[data-workflow-node]")) {
    const nodeId = node.dataset.workflowNode;
    const w = node.offsetWidth;
    const h = node.offsetHeight;
    if (!w || !h) continue;
    for (const socket of node.querySelectorAll(".workflow-socket")) {
      const name = socket.dataset.socket;
      if (!name) continue;
      let t = resolveSocketT(nodeId, name, w, h);
      const key = socketKey(nodeId, name);
      if (socket.dataset.defaultY && !socketLayout[key]) {
        const y = Number.parseFloat(socket.dataset.defaultY);
        if (Number.isFinite(y)) {
          const onLeft = isInputSocket(name);
          const x = onLeft ? 0 : w;
          t = pointToT(x, y * h, w, h);
        }
      }
      positionSocketElement(socket, t, w, h);
    }
  }
}

function setWorkflowTool(tool) {
  if (tool === "anchor") workflowTool = "anchor";
  else if (tool === "resize") workflowTool = "resize";
  else workflowTool = "pan";
  const viewport = document.getElementById("workflowViewport");
  viewport?.classList.toggle("is-tool-anchor", workflowTool === "anchor");
  viewport?.classList.toggle("is-tool-resize", workflowTool === "resize");
  viewport?.classList.toggle("is-tool-pan", workflowTool === "pan");
  for (const button of document.querySelectorAll("[data-workflow-tool]")) {
    const selected = button.dataset.workflowTool === workflowTool;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function endResizeDrag() {
  if (!resizeState) return;
  const node = resizeState.node;
  const payload = {
    nodeId: resizeState.nodeId,
    w: resizeState.latestW,
    h: resizeState.latestH,
    paintingOnly: false,
  };
  node?.classList.remove("is-resizing");
  resizeState = null;
  document.removeEventListener("pointermove", onResizePointerMove);
  document.removeEventListener("pointerup", endResizeDrag);
  document.removeEventListener("pointercancel", endResizeDrag);
  onResizeComplete(payload);
}

function onResizePointerMove(event) {
  if (!resizeState) return;
  const { node, nodeId, mode, startX, startY, originW, originH } = resizeState;
  const scale = resizeState.scale || 1;
  const dx = (event.clientX - startX) / scale;
  const dy = (event.clientY - startY) / scale;
  let w = originW;
  let h = originH;
  if (mode === "e" || mode === "se") w = Math.min(MAX_NODE_W, Math.max(MIN_NODE_W, originW + dx));
  if (mode === "s" || mode === "se") h = Math.min(MAX_NODE_H, Math.max(MIN_NODE_H, originH + dy));
  node.style.width = `${Math.round(w)}px`;
  node.style.height = `${Math.round(h)}px`;
  node.classList.add("workflow-node--sized");
  resizeState.latestW = w;
  resizeState.latestH = h;
  applySocketLayouts();
  onResizeComplete({ nodeId, w, h, paintingOnly: true });
}

function viewportScale() {
  const world = document.getElementById("workflowWorld");
  const style = world?.style.transform || "";
  const scaleMatch = style.match(/scale\(([\d.]+)\)/);
  return scaleMatch ? Number.parseFloat(scaleMatch[1]) : 1;
}

function startResizeDrag(handle, event) {
  if (workflowTool !== "resize" || event.button !== 0) return;
  const node = handle.closest("[data-workflow-node]");
  if (!node) return;
  const nodeId = node.dataset.workflowNode;
  const mode = handle.dataset.resize;
  if (!nodeId || !mode) return;
  event.preventDefault();
  event.stopPropagation();
  const rect = node.getBoundingClientRect();
  resizeState = {
    node,
    nodeId,
    mode,
    startX: event.clientX,
    startY: event.clientY,
    originW: rect.width,
    originH: rect.height,
    latestW: rect.width,
    latestH: rect.height,
    scale: viewportScale(),
  };
  node.classList.add("is-resizing");
  document.addEventListener("pointermove", onResizePointerMove);
  document.addEventListener("pointerup", endResizeDrag);
  document.addEventListener("pointercancel", endResizeDrag);
}

function endAnchorDrag() {
  if (!anchorDrag) return;
  saveSocketLayout();
  anchorDrag = null;
  document.removeEventListener("pointermove", onAnchorPointerMove);
  document.removeEventListener("pointerup", endAnchorDrag);
  document.removeEventListener("pointercancel", endAnchorDrag);
  onAnchorMoved();
}

function onAnchorPointerMove(event) {
  if (!anchorDrag) return;
  const { socket, node, nodeId, socketName } = anchorDrag;
  const rect = node.getBoundingClientRect();
  const w = rect.width;
  const h = rect.height;
  const px = event.clientX - rect.left;
  const py = event.clientY - rect.top;
  const { t } = closestPointOnPerimeter(px, py, w, h);
  positionSocketElement(socket, t, w, h);
  socketLayout[socketKey(nodeId, socketName)] = { t };
  onAnchorMoved();
}

function startAnchorDrag(socket, event) {
  const node = socket.closest("[data-workflow-node]");
  if (!node) return;
  const nodeId = node.dataset.workflowNode;
  const socketName = socket.dataset.socket;
  if (!nodeId || !socketName) return;
  event.preventDefault();
  event.stopPropagation();
  anchorDrag = { socket, node, nodeId, socketName };
  document.addEventListener("pointermove", onAnchorPointerMove);
  document.addEventListener("pointerup", endAnchorDrag);
  document.addEventListener("pointercancel", endAnchorDrag);
}

export function bindWorkflowTools(options = {}) {
  if (toolsBound) return;
  toolsBound = true;
  onAnchorMoved = typeof options.onAnchorMoved === "function" ? options.onAnchorMoved : () => {};
  onResizeComplete = typeof options.onResizeComplete === "function" ? options.onResizeComplete : () => {};
  loadSocketLayout();
  applySocketLayouts();
  setWorkflowTool("pan");

  for (const button of document.querySelectorAll("[data-workflow-tool]")) {
    button.addEventListener("click", () => setWorkflowTool(button.dataset.workflowTool));
  }

  const layer = document.getElementById("workflowNodeLayer");
  layer?.addEventListener("pointerdown", (event) => {
    if (workflowTool === "resize" && event.button === 0) {
      const handle = event.target.closest(".workflow-resize-handle");
      if (handle) {
        startResizeDrag(handle, event);
        return;
      }
    }
    if (workflowTool !== "anchor" || event.button !== 0) return;
    const socket = event.target.closest(".workflow-socket");
    if (!socket) return;
    startAnchorDrag(socket, event);
  });
}

export function workflowToolBlocksNodeDrag() {
  return workflowTool === "anchor" || workflowTool === "resize";
}