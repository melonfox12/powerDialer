import {
  getWorkflowTool,
  isWorkflowInputSocket,
  isWorkflowOutputSocket,
} from "./tools.js";

const SVG_NS = "http://www.w3.org/2000/svg";

/** @type {null | { fromNode: string, fromSocket: string, startX: number, startY: number, pointerId: number }} */
let wireState = null;
let wireBound = false;
/** @type {SVGPathElement | null} */
let previewPath = null;

let getSocketLayerPoint = () => null;
let layerPointFromClient = () => ({ x: 0, y: 0 });
let buildWirePathD = () => "";
let tryAddEdge = () => false;
let onWireFrame = () => {};
let listEdges = () => [];

function edgesSvg() {
  return document.getElementById("workflowEdges");
}

function viewport() {
  return document.getElementById("workflowViewport");
}

export function isWorkflowWiring() {
  return Boolean(wireState);
}

function clearWireTargetHighlights() {
  for (const el of document.querySelectorAll(".workflow-socket.is-wire-target")) {
    el.classList.remove("is-wire-target", "is-wire-target-valid");
  }
}

function edgeAlreadyExists(from, fromSocket, to, toSocket) {
  return listEdges().some(
    (edge) =>
      edge.from === from &&
      edge.fromSocket === fromSocket &&
      edge.to === to &&
      edge.toSocket === toSocket,
  );
}

function orientedEdge(fromNode, fromSocket, toNode, toSocket) {
  if (fromNode === toNode) return null;
  if (isWorkflowOutputSocket(fromSocket) && isWorkflowInputSocket(toSocket)) {
    return { from: fromNode, fromSocket, to: toNode, toSocket };
  }
  if (isWorkflowInputSocket(fromSocket) && isWorkflowOutputSocket(toSocket)) {
    return { from: toNode, fromSocket: toSocket, to: fromNode, toSocket: fromSocket };
  }
  return null;
}

function socketFromElement(el) {
  const socket = el?.closest?.(".workflow-socket");
  if (!socket) return null;
  const node = socket.closest("[data-workflow-node]");
  if (!node) return null;
  const nodeId = node.dataset.workflowNode;
  const socketName = socket.dataset.socket;
  if (!nodeId || !socketName) return null;
  return { socket, nodeId, socketName };
}

function ensurePreviewPath() {
  const svg = edgesSvg();
  if (!svg) return null;
  if (!previewPath) {
    previewPath = document.createElementNS(SVG_NS, "path");
    previewPath.setAttribute("class", "workflow-edge workflow-edge--preview");
    previewPath.setAttribute("fill", "none");
    svg.appendChild(previewPath);
  }
  return previewPath;
}

function hidePreviewPath() {
  previewPath?.setAttribute("d", "");
}

function paintWirePreview(clientX, clientY) {
  if (!wireState) return;
  const path = ensurePreviewPath();
  if (!path) return;
  const end = layerPointFromClient(clientX, clientY);
  path.setAttribute("d", buildWirePathD(wireState.startX, wireState.startY, end.x, end.y));
}

function highlightDropTarget(clientX, clientY) {
  clearWireTargetHighlights();
  if (!wireState) return;
  const hit = document.elementFromPoint(clientX, clientY);
  const target = socketFromElement(hit);
  if (!target || target.nodeId === wireState.fromNode) return;
  const edge = orientedEdge(wireState.fromNode, wireState.fromSocket, target.nodeId, target.socketName);
  target.socket.classList.add("is-wire-target");
  if (edge && !edgeAlreadyExists(edge.from, edge.fromSocket, edge.to, edge.toSocket)) {
    target.socket.classList.add("is-wire-target-valid");
  }
}

function endWire(event) {
  if (!wireState) return;
  const hit = document.elementFromPoint(event.clientX, event.clientY);
  const target = socketFromElement(hit);
  if (target) {
    const edge = orientedEdge(wireState.fromNode, wireState.fromSocket, target.nodeId, target.socketName);
    if (edge && !edgeAlreadyExists(edge.from, edge.fromSocket, edge.to, edge.toSocket)) {
      tryAddEdge(edge);
    }
  }
  const captureEl = wireState.socketEl;
  wireState = null;
  captureEl?.releasePointerCapture?.(event.pointerId);
  hidePreviewPath();
  clearWireTargetHighlights();
  viewport()?.classList.remove("is-wiring");
  document.removeEventListener("pointermove", onWirePointerMove);
  document.removeEventListener("pointerup", endWire);
  document.removeEventListener("pointercancel", endWire);
  onWireFrame();
}

function onWirePointerMove(event) {
  if (!wireState || wireState.pointerId !== event.pointerId) return;
  event.preventDefault();
  paintWirePreview(event.clientX, event.clientY);
  highlightDropTarget(event.clientX, event.clientY);
  onWireFrame();
}

function startWire(socket, event) {
  if (event.button !== 0 || getWorkflowTool() !== "pan") return;
  const node = socket.closest("[data-workflow-node]");
  if (!node) return;
  const nodeId = node.dataset.workflowNode;
  const socketName = socket.dataset.socket;
  if (!nodeId || !socketName) return;

  const start = getSocketLayerPoint(nodeId, socketName);
  if (!start) return;

  event.preventDefault();
  event.stopPropagation();

  wireState = {
    fromNode: nodeId,
    fromSocket: socketName,
    startX: start.x,
    startY: start.y,
    pointerId: event.pointerId,
    socketEl: socket,
  };
  viewport()?.classList.add("is-wiring");
  paintWirePreview(event.clientX, event.clientY);
  socket.setPointerCapture?.(event.pointerId);
  document.addEventListener("pointermove", onWirePointerMove);
  document.addEventListener("pointerup", endWire);
  document.addEventListener("pointercancel", endWire);
  onWireFrame();
}

export function bindWorkflowConnections(options = {}) {
  if (wireBound) return;
  wireBound = true;
  getSocketLayerPoint = typeof options.getSocketLayerPoint === "function" ? options.getSocketLayerPoint : () => null;
  layerPointFromClient = typeof options.layerPointFromClient === "function" ? options.layerPointFromClient : () => ({ x: 0, y: 0 });
  buildWirePathD = typeof options.buildWirePathD === "function" ? options.buildWirePathD : () => "";
  tryAddEdge = typeof options.tryAddEdge === "function" ? options.tryAddEdge : () => false;
  onWireFrame = typeof options.onWireFrame === "function" ? options.onWireFrame : () => {};
  listEdges = typeof options.listEdges === "function" ? options.listEdges : () => [];

  const layer = document.getElementById("workflowNodeLayer");
  layer?.addEventListener(
    "pointerdown",
    (event) => {
      if (getWorkflowTool() !== "pan") return;
      const socket = event.target.closest(".workflow-socket");
      if (!socket) return;
      startWire(socket, event);
    },
    { capture: true },
  );
}