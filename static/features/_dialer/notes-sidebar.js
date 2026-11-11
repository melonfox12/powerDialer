import { dialerEls, humanDialerPanel } from "../../_core/format.js";

const STORAGE_WIDTH = "dialerNotesWidth";
const STORAGE_COLLAPSED = "dialerNotesCollapsed";
const MIN_WIDTH = 280;
const MAX_WIDTH = 720;
const DEFAULT_WIDTH = 400;
const COLLAPSED_WIDTH = 44;

let bound = false;

function workspacePanels() {
  const panel = humanDialerPanel();
  return panel ? [panel] : [];
}

function clampWidth(value) {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(value)));
}

function readSavedWidth() {
  const stored = Number(localStorage.getItem(STORAGE_WIDTH));
  return clampWidth(Number.isFinite(stored) && stored > 0 ? stored : DEFAULT_WIDTH);
}

function applyWidth(widthPx) {
  const px = `${clampWidth(widthPx)}px`;
  for (const panel of workspacePanels()) {
    panel.style.setProperty("--dialer-notes-width", px);
  }
  localStorage.setItem(STORAGE_WIDTH, String(clampWidth(widthPx)));
}

function setCollapsed(collapsed) {
  for (const panel of workspacePanels()) {
    panel.classList.toggle("notes-collapsed", collapsed);
    panel.dataset.notesCollapsed = collapsed ? "true" : "false";
  }
  localStorage.setItem(STORAGE_COLLAPSED, collapsed ? "1" : "0");
  for (const collapseBtn of dialerEls("prospectNotesCollapse")) {
    collapseBtn.hidden = collapsed;
    collapseBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
  }
  for (const expandTab of dialerEls("prospectNotesExpandTab")) {
    expandTab.hidden = !collapsed;
  }
  if (collapsed) {
    const collapsedPx = `${COLLAPSED_WIDTH}px`;
    for (const panel of workspacePanels()) {
      panel.style.setProperty("--dialer-notes-width", collapsedPx);
    }
  } else {
    applyWidth(readSavedWidth());
  }
}

function restoreLayout() {
  const collapsed = localStorage.getItem(STORAGE_COLLAPSED) === "1";
  if (collapsed) setCollapsed(true);
  else applyWidth(readSavedWidth());
}

function bindResizeHandle() {
  for (const handle of dialerEls("prospectNotesResizeHandle")) {
    const panel = handle.closest(".dialer-run-panel");
    if (!panel) continue;

    const nudge = (delta) => {
      if (panel.classList.contains("notes-collapsed")) setCollapsed(false);
      const shell = panel.querySelector(".prospect-notes-shell");
      const current = shell?.getBoundingClientRect().width ?? readSavedWidth();
      applyWidth(current + delta);
    };

    handle.addEventListener("keydown", (event) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        nudge(16);
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        nudge(-16);
      }
    });

    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      handle.setPointerCapture(event.pointerId);
      handle.classList.add("is-dragging");
      if (panel.classList.contains("notes-collapsed")) setCollapsed(false);
      const startX = event.clientX;
      const shell = panel.querySelector(".prospect-notes-shell");
      const startWidth = shell?.getBoundingClientRect().width || readSavedWidth();

      const onMove = (moveEvent) => {
        const delta = startX - moveEvent.clientX;
        applyWidth(startWidth + delta);
      };

      const onUp = (upEvent) => {
        handle.classList.remove("is-dragging");
        if (handle.hasPointerCapture(upEvent.pointerId)) {
          handle.releasePointerCapture(upEvent.pointerId);
        }
        handle.removeEventListener("pointermove", onMove);
        handle.removeEventListener("pointerup", onUp);
        handle.removeEventListener("pointercancel", onUp);
      };

      handle.addEventListener("pointermove", onMove);
      handle.addEventListener("pointerup", onUp);
      handle.addEventListener("pointercancel", onUp);
    });
  }
}

export function bindNotesSidebar() {
  if (bound) return;
  bound = true;
  restoreLayout();
  bindResizeHandle();
  for (const btn of dialerEls("prospectNotesCollapse")) {
    btn.addEventListener("click", () => setCollapsed(true));
  }
  for (const btn of dialerEls("prospectNotesExpandTab")) {
    btn.addEventListener("click", () => setCollapsed(false));
  }
}
