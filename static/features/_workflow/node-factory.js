import { WORKFLOW_LANES, workflowTemplateById } from "./node-catalog.js";
import { nodeLeadCount } from "./campaign-flow.js";

const INFO_ICON =
  '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.25"/><path d="M8 7.1v4.2M8 5.5v.1" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>';

function slugSocket(label, index) {
  const slug = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return slug || `out-${index}`;
}

function socketFraction(index, total) {
  if (total <= 1) return 0.5;
  return 0.22 + (index / Math.max(1, total - 1)) * 0.56;
}

/** @param {import("./node-catalog.js").WorkflowNodeTemplate} template */
function isEndType(template) {
  return template.type === "End";
}

/** @param {import("./node-catalog.js").WorkflowNodeTemplate} template */
function isSourceType(template) {
  return template.type === "Source";
}

/**
 * @param {string} instanceId
 * @param {string} templateId
 * @param {{ w?: number, h?: number }} [size]
 */
export function buildWorkflowNodeElement(instanceId, templateId, size = {}) {
  const template = workflowTemplateById(templateId);
  if (!template) return null;

  const lane = WORKFLOW_LANES[template.lane];
  const laneCss = lane?.css ?? "lane-prep";

  const article = document.createElement("article");
  article.className = `workflow-node workflow-node--${laneCss}`;
  article.dataset.workflowNode = instanceId;
  article.dataset.workflowTemplate = templateId;

  if (size.w) article.style.width = `${size.w}px`;
  if (size.h) {
    article.style.height = `${size.h}px`;
    article.classList.add("workflow-node--sized");
  }

  const outputsLine = template.outputs.join(", ");
  const leadCount = nodeLeadCount(templateId);
  const header = document.createElement("header");
  header.className = "workflow-node-header";
  header.innerHTML = `
    <div class="workflow-node-header-top">
      <span class="workflow-node-tag workflow-node-tag--${laneCss}">${template.type}</span>
      <span class="workflow-node-lane-label">${lane?.label ?? template.lane}</span>
      <button type="button" class="workflow-node-info-btn" data-workflow-node-info="${templateId}" aria-label="About ${template.title}">${INFO_ICON}</button>
    </div>
    <h3 class="workflow-node-title">${template.title}</h3>
  `;

  const body = document.createElement("div");
  body.className = "workflow-node-body";
  body.innerHTML = `
    <p class="workflow-stat workflow-node-lead-count"><strong>Leads here:</strong> <span data-workflow-node-count>${leadCount}</span></p>
    <p class="workflow-stat"><strong>Outputs:</strong> ${outputsLine}</p>
    <p class="workflow-hint"><strong>Shows:</strong> ${template.shows}</p>
  `;

  article.appendChild(header);
  article.appendChild(body);

  if (!isSourceType(template)) {
    const input = document.createElement("span");
    input.className = "workflow-socket workflow-socket-in";
    input.dataset.socket = "in";
    input.title = "Input";
    article.appendChild(input);
  }

  if (!isEndType(template)) {
    const outs = template.outputs;
    const multi = outs.length > 1;
    outs.forEach((label, index) => {
      const socket = document.createElement("span");
      socket.className = `workflow-socket workflow-socket-out${multi ? " workflow-socket-out--multi" : ""}`;
      const name = multi ? `out-${slugSocket(label, index)}` : "out";
      socket.dataset.socket = name;
      socket.title = label;
      if (multi) socket.dataset.defaultY = String(socketFraction(index, outs.length));
      article.appendChild(socket);
    });
  }

  const resizeLayer = document.createElement("div");
  resizeLayer.className = "workflow-node-resize-handles";
  resizeLayer.setAttribute("aria-hidden", "true");
  resizeLayer.innerHTML = `
    <span class="workflow-resize-handle workflow-resize-handle--e" data-resize="e"></span>
    <span class="workflow-resize-handle workflow-resize-handle--s" data-resize="s"></span>
    <span class="workflow-resize-handle workflow-resize-handle--se" data-resize="se"></span>
  `;
  article.appendChild(resizeLayer);

  return article;
}

export function templateInfoPayload(templateId) {
  const template = workflowTemplateById(templateId);
  if (!template) return null;
  const lane = WORKFLOW_LANES[template.lane];
  return {
    title: template.title,
    lane: lane?.label ?? template.lane,
    type: template.type,
    outputs: template.outputs.join(", "),
    shows: template.shows,
    description: template.description,
  };
}