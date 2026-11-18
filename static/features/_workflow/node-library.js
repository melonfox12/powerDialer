import { WORKFLOW_LANES, WORKFLOW_NODE_TEMPLATES } from "./node-catalog.js";
import { templateInfoPayload } from "./node-factory.js";
import { addWorkflowInstance } from "./canvas-nodes.js";

const LIBRARY_WIDTH_KEY = "godial-workflow-library-width";
const LIBRARY_COLLAPSED_KEY = "godial-workflow-library-collapsed";
const MIN_LIBRARY_W = 200;
const MAX_LIBRARY_W = 420;
const DEFAULT_LIBRARY_W = 272;

let libraryBound = false;
let libraryDrag = null;
/** @type {(clientX: number, clientY: number, templateId: string) => void} */
let onPlaced = () => {};

const INFO_ICON =
  '<svg viewBox="0 0 16 16" width="13" height="13" aria-hidden="true"><circle cx="8" cy="8" r="6.25" fill="none" stroke="currentColor" stroke-width="1.25"/><path d="M8 7.1v4.2M8 5.5v.1" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/></svg>';

function libraryEl() {
  return document.getElementById("workflowNodeLibrary");
}

function libraryListEl() {
  return document.getElementById("workflowLibraryList");
}

function filterQuery() {
  return (document.getElementById("workflowLibrarySearch")?.value ?? "").trim().toLowerCase();
}

function matchesSearch(template, q) {
  if (!q) return true;
  const lane = WORKFLOW_LANES[template.lane]?.label ?? "";
  return (
    template.title.toLowerCase().includes(q) ||
    template.type.toLowerCase().includes(q) ||
    lane.toLowerCase().includes(q)
  );
}

function laneSwatchClass(lane) {
  return WORKFLOW_LANES[lane]?.css ?? "lane-prep";
}

function renderLibraryItems() {
  const list = libraryListEl();
  if (!list) return;
  const q = filterQuery();
  list.replaceChildren();
  const grouped = /** @type {Record<string, typeof WORKFLOW_NODE_TEMPLATES>} */ ({});
  for (const template of WORKFLOW_NODE_TEMPLATES) {
    if (!matchesSearch(template, q)) continue;
    const laneKey = template.lane;
    if (!grouped[laneKey]) grouped[laneKey] = [];
    grouped[laneKey].push(template);
  }
  const laneOrder = ["prep", "ai-calling", "decide", "crm"];
  for (const laneKey of laneOrder) {
    const items = grouped[laneKey];
    if (!items?.length) continue;
    const lane = WORKFLOW_LANES[laneKey];
    const section = document.createElement("section");
    section.className = "workflow-library-section";
    section.innerHTML = `<h4 class="workflow-library-section-title workflow-library-section-title--${laneSwatchClass(laneKey)}">${lane?.label ?? laneKey}</h4>`;
    const body = document.createElement("div");
    body.className = "workflow-library-section-body";
    for (const template of items) {
      const row = document.createElement("div");
      row.className = "workflow-library-item";
      row.dataset.templateId = template.id;
      row.innerHTML = `
        <button type="button" class="workflow-library-preview workflow-library-preview--${laneSwatchClass(template.lane)}" data-library-drag="${template.id}" title="Drag to canvas" aria-label="Drag ${template.title} to canvas">
          <span class="workflow-library-preview-tag">${template.type}</span>
          <span class="workflow-library-preview-title">${template.title}</span>
        </button>
        <span class="workflow-library-item-name">${template.title}</span>
        <button type="button" class="workflow-library-info" data-library-info="${template.id}" aria-label="About ${template.title}">${INFO_ICON}</button>
        <div class="workflow-library-info-pop" role="tooltip" hidden></div>
      `;
      body.appendChild(row);
    }
    section.appendChild(body);
    list.appendChild(section);
  }
  if (!list.childElementCount) {
    const empty = document.createElement("p");
    empty.className = "workflow-library-empty";
    empty.textContent = "No nodes match your search.";
    list.appendChild(empty);
  }
}

function showNodeInfoDialog(templateId) {
  const dialog = document.getElementById("workflowNodeInfoDialog");
  const title = document.getElementById("workflowNodeInfoTitle");
  const body = document.getElementById("workflowNodeInfoBody");
  if (!dialog || !title || !body) return;
  const info = templateInfoPayload(templateId);
  if (!info) return;
  title.textContent = info.title;
  body.innerHTML = `
    <p class="workflow-info-meta"><strong>Lane:</strong> ${info.lane} · <strong>Type:</strong> ${info.type}</p>
    <p class="workflow-info-meta"><strong>Outputs:</strong> ${info.outputs}</p>
    <p class="workflow-info-meta"><strong>Shows:</strong> ${info.shows}</p>
    <p class="workflow-hint">${info.description}</p>
  `;
  if (typeof dialog.showModal === "function") dialog.showModal();
}

function bindLibraryInfoPopovers() {
  const list = libraryListEl();
  list?.addEventListener("mouseover", (event) => {
    const btn = event.target.closest("[data-library-info]");
    if (!btn) return;
    const row = btn.closest(".workflow-library-item");
    const pop = row?.querySelector(".workflow-library-info-pop");
    const templateId = btn.dataset.libraryInfo;
    const info = templateInfoPayload(templateId);
    if (!pop || !info) return;
    pop.hidden = false;
    pop.innerHTML = `<strong>${info.title}</strong><span>${info.description}</span>`;
  });
  list?.addEventListener("mouseout", (event) => {
    const btn = event.target.closest("[data-library-info]");
    if (!btn) return;
    const related = event.relatedTarget;
    if (related && btn.contains(related)) return;
    const row = btn.closest(".workflow-library-item");
    const pop = row?.querySelector(".workflow-library-info-pop");
    if (pop) pop.hidden = true;
  });
  list?.addEventListener("click", (event) => {
    const infoBtn = event.target.closest("[data-library-info]");
    if (infoBtn) {
      event.preventDefault();
      showNodeInfoDialog(infoBtn.dataset.libraryInfo);
    }
  });
}

function setLibraryWidth(px) {
  const lib = libraryEl();
  if (!lib) return;
  const w = Math.min(MAX_LIBRARY_W, Math.max(MIN_LIBRARY_W, px));
  lib.style.setProperty("--workflow-library-width", `${w}px`);
  try {
    localStorage.setItem(LIBRARY_WIDTH_KEY, String(w));
  } catch {
    // ignore
  }
}

function loadLibraryLayout() {
  const lib = libraryEl();
  if (!lib) return;
  try {
    const savedW = Number.parseInt(localStorage.getItem(LIBRARY_WIDTH_KEY) || "", 10);
    if (Number.isFinite(savedW)) setLibraryWidth(savedW);
    else setLibraryWidth(DEFAULT_LIBRARY_W);
    const collapsed = localStorage.getItem(LIBRARY_COLLAPSED_KEY) === "1";
    lib.classList.toggle("is-collapsed", collapsed);
    document.getElementById("workflowLibraryCollapseBtn")?.setAttribute("aria-expanded", String(!collapsed));
  } catch {
    setLibraryWidth(DEFAULT_LIBRARY_W);
  }
}

function toggleLibraryCollapsed() {
  const lib = libraryEl();
  if (!lib) return;
  const next = !lib.classList.contains("is-collapsed");
  lib.classList.toggle("is-collapsed", next);
  const btn = document.getElementById("workflowLibraryCollapseBtn");
  btn?.setAttribute("aria-expanded", String(!next));
  try {
    localStorage.setItem(LIBRARY_COLLAPSED_KEY, next ? "1" : "0");
  } catch {
    // ignore
  }
}

function endLibraryResize() {
  if (!libraryDrag) return;
  libraryDrag = null;
  document.body.classList.remove("is-workflow-library-resizing");
  document.removeEventListener("pointermove", onLibraryResizeMove);
  document.removeEventListener("pointerup", endLibraryResize);
  document.removeEventListener("pointercancel", endLibraryResize);
}

function onLibraryResizeMove(event) {
  if (!libraryDrag) return;
  const delta = event.clientX - libraryDrag.originX;
  setLibraryWidth(libraryDrag.originW + delta);
}

function startLibraryResize(event) {
  if (event.button !== 0) return;
  const lib = libraryEl();
  if (!lib || lib.classList.contains("is-collapsed")) return;
  event.preventDefault();
  const w = lib.getBoundingClientRect().width;
  libraryDrag = { originX: event.clientX, originW: w };
  document.body.classList.add("is-workflow-library-resizing");
  document.addEventListener("pointermove", onLibraryResizeMove);
  document.addEventListener("pointerup", endLibraryResize);
  document.addEventListener("pointercancel", endLibraryResize);
}

function clientToWorldPlacement(clientX, clientY) {
  const viewport = document.getElementById("workflowViewport");
  const world = document.getElementById("workflowWorld");
  if (!viewport || !world) return { x: 120, y: 120 };
  const style = world.style.transform || "";
  const scaleMatch = style.match(/scale\(([\d.]+)\)/);
  const scale = scaleMatch ? Number.parseFloat(scaleMatch[1]) : 1;
  const panMatch = style.match(/translate3d\(([-\d.]+)px,\s*([-\d.]+)px/);
  const panX = panMatch ? Number.parseFloat(panMatch[1]) : 0;
  const panY = panMatch ? Number.parseFloat(panMatch[2]) : 0;
  const rect = viewport.getBoundingClientRect();
  const displayX = (clientX - rect.left - panX) / scale;
  const displayY = (clientY - rect.top - panY) / scale;
  const originX = Number.parseFloat(world.dataset.canvasOriginX || "0");
  const originY = Number.parseFloat(world.dataset.canvasOriginY || "0");
  return { x: displayX + originX, y: displayY + originY };
}

function endLibraryNodeDrag() {
  if (!libraryDrag?.templateId) return;
  const { templateId, lastX, lastY, dropped } = libraryDrag;
  libraryDrag = null;
  document.body.classList.remove("is-workflow-library-dragging");
  document.getElementById("workflowLibraryDragGhost")?.remove();
  document.removeEventListener("pointermove", onLibraryNodeDragMove);
  document.removeEventListener("pointerup", endLibraryNodeDrag);
  document.removeEventListener("pointercancel", endLibraryNodeDrag);
  const viewport = document.getElementById("workflowViewport");
  if (!dropped || !viewport) return;
  const rect = viewport.getBoundingClientRect();
  const inside =
    lastX >= rect.left && lastX <= rect.right && lastY >= rect.top && lastY <= rect.bottom;
  if (!inside) return;
  const pt = clientToWorldPlacement(lastX, lastY);
  const row = addWorkflowInstance(templateId, pt.x - 134, pt.y - 40);
  if (row) onPlaced(row);
}

function onLibraryNodeDragMove(event) {
  if (!libraryDrag?.templateId) return;
  libraryDrag.lastX = event.clientX;
  libraryDrag.lastY = event.clientY;
  libraryDrag.dropped = true;
  const ghost = document.getElementById("workflowLibraryDragGhost");
  if (ghost) {
    ghost.style.left = `${event.clientX}px`;
    ghost.style.top = `${event.clientY}px`;
  }
}

function startLibraryNodeDrag(previewBtn, event) {
  if (event.button !== 0) return;
  const templateId = previewBtn.dataset.libraryDrag;
  if (!templateId) return;
  event.preventDefault();
  const template = WORKFLOW_NODE_TEMPLATES.find((t) => t.id === templateId);
  const ghost = document.createElement("div");
  ghost.id = "workflowLibraryDragGhost";
  ghost.className = `workflow-library-drag-ghost workflow-library-preview--${laneSwatchClass(template?.lane ?? "prep")}`;
  ghost.innerHTML = `<span class="workflow-library-preview-tag">${template?.type ?? ""}</span><span class="workflow-library-preview-title">${template?.title ?? ""}</span>`;
  ghost.style.left = `${event.clientX}px`;
  ghost.style.top = `${event.clientY}px`;
  document.body.appendChild(ghost);
  libraryDrag = { templateId, lastX: event.clientX, lastY: event.clientY, dropped: false };
  document.body.classList.add("is-workflow-library-dragging");
  document.addEventListener("pointermove", onLibraryNodeDragMove);
  document.addEventListener("pointerup", endLibraryNodeDrag);
  document.addEventListener("pointercancel", endLibraryNodeDrag);
}

export function bindNodeLibrary({ onInstancePlaced } = {}) {
  if (libraryBound) {
    renderLibraryItems();
    return;
  }
  libraryBound = true;
  onPlaced = typeof onInstancePlaced === "function" ? onInstancePlaced : () => {};

  loadLibraryLayout();
  renderLibraryItems();

  document.getElementById("workflowLibrarySearch")?.addEventListener("input", () => renderLibraryItems());
  document.getElementById("workflowLibraryCollapseBtn")?.addEventListener("click", () => toggleLibraryCollapsed());
  document.getElementById("workflowLibraryResizer")?.addEventListener("pointerdown", startLibraryResize);
  bindLibraryInfoPopovers();

  libraryListEl()?.addEventListener("pointerdown", (event) => {
    const preview = event.target.closest("[data-library-drag]");
    if (preview) startLibraryNodeDrag(preview, event);
  });

  document.getElementById("workflowNodeLayer")?.addEventListener("click", (event) => {
    const infoBtn = event.target.closest("[data-workflow-node-info]");
    if (!infoBtn) return;
    event.preventDefault();
    event.stopPropagation();
    showNodeInfoDialog(infoBtn.dataset.workflowNodeInfo);
  });
}

export function refreshNodeLibrary() {
  renderLibraryItems();
}