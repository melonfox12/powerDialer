/** @typedef {{ type: "node", nodeId: string } | { type: "edge", edgeId: string, from: string, to: string } | { type: "lead", leadId: string, via: "node" | "edge", contextId: string }} WorkflowSelection */

/** @type {WorkflowSelection | null} */
let selection = null;

export function getWorkflowSelection() {
  return selection;
}

function canvasBusy() {
  const view = document.getElementById("workflowViewport");
  return Boolean(view?.classList.contains("is-workflow-interacting") || view?.classList.contains("is-panning"));
}

export function setWorkflowSelection(next) {
  selection = next;
  if (canvasBusy()) return;
  window.dispatchEvent(new CustomEvent("godial-workflow-selection"));
}

export function flushWorkflowSelectionRender() {
  if (!selection || canvasBusy()) return;
  window.dispatchEvent(new CustomEvent("godial-workflow-selection"));
}

export function clearWorkflowSelection() {
  if (!selection) return;
  selection = null;
  window.dispatchEvent(new CustomEvent("godial-workflow-selection"));
}