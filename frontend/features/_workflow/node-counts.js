import { nodeLeadCount } from "./flow-snapshot.js";

export function paintWorkflowNodeCounts() {
  for (const node of document.querySelectorAll("[data-workflow-node]")) {
    const templateId = node.dataset.workflowTemplate;
    const target = node.querySelector("[data-workflow-node-count]");
    if (!templateId || !target) continue;
    target.textContent = String(nodeLeadCount(templateId));
  }
}