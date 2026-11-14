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
/** @type {Record<string, { t?: number, y?: number }>} */
let socketLayout = {};
let anchorDrag = null;
let toolsBound = false;
let onAnchorMoved = () => {};

function isInputSocket(name) {
  return name === "in" || name.startsWith("in-");
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
      const t = resolveSocketT(nodeId, name, w, h);
      positionSocketElement(socket, t, w, h);
    }
  }
}

function setWorkflowTool(tool) {
  workflowTool = tool === "anchor" ? "anchor" : "pan";
  const viewport = document.getElementById("workflowViewport");
  viewport?.classList.toggle("is-tool-anchor", workflowTool === "anchor");
  viewport?.classList.toggle("is-tool-pan", workflowTool === "pan");
  for (const button of document.querySelectorAll("[data-workflow-tool]")) {
    const selected = button.dataset.workflowTool === workflowTool;
    button.classList.toggle("is-selected", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
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
  loadSocketLayout();
  applySocketLayouts();
  setWorkflowTool("pan");

  for (const button of document.querySelectorAll("[data-workflow-tool]")) {
    button.addEventListener("click", () => setWorkflowTool(button.dataset.workflowTool));
  }

  const layer = document.getElementById("workflowNodeLayer");
  layer?.addEventListener("pointerdown", (event) => {
    if (workflowTool !== "anchor" || event.button !== 0) return;
    const socket = event.target.closest(".workflow-socket");
    if (!socket) return;
    startAnchorDrag(socket, event);
  });
}

export function workflowToolBlocksNodeDrag() {
  return workflowTool === "anchor";
}