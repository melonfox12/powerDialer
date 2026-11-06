import { postJson } from "../../_core/api.js";
import { applyMutationPayload } from "../../_core/sync-state.js";
import {
  PIPELINE_LOCKED_STEP_KEYS,
  formatPipelineStepKey,
  getPipelineSteps,
  byId,
} from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { pipelineCustomStepsFromCatalog } from "./pipeline-steps.js";
import { render } from "../../core.js";
import { S, state } from "../../_core/state.js";

let editorBound = false;
/** Matches state.pipeline_revision last painted into the step editor (null = never). */
let lastRenderedEditorRevision = null;

function pipelineEditorFieldFocused() {
  const details = byId("pipelineStepsEditor");
  if (!details?.open) return false;
  const active = document.activeElement;
  if (!active || !details.contains(active)) return false;
  const tag = active.tagName;
  if (tag === "TEXTAREA" || tag === "SELECT") return true;
  if (tag === "INPUT") {
    const type = (active.getAttribute("type") || "text").toLowerCase();
    return type === "text" || type === "number" || type === "" || type === "search";
  }
  return false;
}

function rowsFromEditor() {
  const list = byId("pipelineStepsEditorList");
  if (!list) return [];
  const rows = [];
  for (const row of list.querySelectorAll(".pipeline-editor-row")) {
    rows.push({
      key: row.querySelector(".pipeline-editor-key")?.value?.trim() || "",
      label: row.querySelector(".pipeline-editor-label")?.value?.trim() || "",
      wait_hours: Number(row.querySelector(".pipeline-editor-wait")?.value) || 0,
    });
  }
  return rows;
}

function applyKeyFormattingToInput(keyInput) {
  const raw = keyInput.value;
  const formatted = formatPipelineStepKey(raw);
  if (formatted && formatted !== raw.trim()) keyInput.value = formatted;
  return formatted || raw.trim();
}

function renderEditorRows(rows) {
  const list = byId("pipelineStepsEditorList");
  if (!list) return;
  list.replaceChildren();
  for (let i = 0; i < rows.length; i += 1) {
    const row = document.createElement("div");
    row.className = "pipeline-editor-row";
    const keyInput = document.createElement("input");
    keyInput.type = "text";
    keyInput.className = "pipeline-editor-key";
    keyInput.value = rows[i].key;
    keyInput.setAttribute("aria-label", "Step key");
    keyInput.title = "Spaces and punctuation become underscores; saved as lowercase. Fixed on blur.";
    keyInput.addEventListener("blur", () => applyKeyFormattingToInput(keyInput));
    const labelInput = document.createElement("input");
    labelInput.type = "text";
    labelInput.className = "pipeline-editor-label";
    labelInput.value = rows[i].label;
    labelInput.setAttribute("aria-label", "Step label");
    const waitInput = document.createElement("input");
    waitInput.type = "number";
    waitInput.min = "0";
    waitInput.max = "8760";
    waitInput.className = "pipeline-editor-wait";
    waitInput.value = String(rows[i].wait_hours ?? 36);
    waitInput.setAttribute("aria-label", "Wait hours before next step");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "button button-quiet";
    del.textContent = "Remove";
    del.addEventListener("click", () => {
      const next = rowsFromEditor();
      next.splice(i, 1);
      renderEditorRows(next);
    });
    row.append(keyInput, labelInput, waitInput, del);
    list.append(row);
  }
}

export function renderPipelineEditor() {
  const rows = pipelineCustomStepsFromCatalog(getPipelineSteps()).map((s) => ({
    key: String(s.key || ""),
    label: String(s.label || ""),
    wait_hours: Number(s.wait_hours) || 0,
  }));
  renderEditorRows(rows);
  lastRenderedEditorRevision = state.pipeline_revision ?? null;
}

/** When the server/catalog pipeline schema changes, refresh the editor rows to match the board. */
export function refreshPipelineEditorIfStale() {
  if (S.dashboardTab !== "pipeline") return;
  if (pipelineEditorFieldFocused()) return;
  const rev = state.pipeline_revision ?? null;
  if (rev === lastRenderedEditorRevision) return;
  renderPipelineEditor();
}

async function savePipelineSteps() {
  const migrate = byId("pipelineMigrateLeadsInput")?.checked ?? false;
  const list = byId("pipelineStepsEditorList");
  const keyInputs = list ? [...list.querySelectorAll(".pipeline-editor-key")] : [];
  for (const keyInput of keyInputs) applyKeyFormattingToInput(keyInput);
  const rows = rowsFromEditor();
  for (const item of rows) {
    if (!item.label?.trim()) {
      showToast("Each step needs a key and a label.", true);
      return;
    }
    const normalized = formatPipelineStepKey(item.key);
    if (!normalized) {
      showToast("Use letters or numbers in the key (e.g. follow_up_2).", true);
      return;
    }
    item.key = normalized;
    if (PIPELINE_LOCKED_STEP_KEYS.includes(item.key)) {
      showToast("Dialed and Contacted (engaged) are fixed — use other keys.", true);
      return;
    }
  }
  const keys = new Set(rows.map((r) => r.key));
  if (keys.size !== rows.length) {
    showToast("Duplicate step keys.", true);
    return;
  }
  const normalized = rows.map((r) => ({
    key: r.key,
    label: r.label,
    wait_hours: Math.min(8760, Math.max(0, Math.floor(Number(r.wait_hours) || 0))),
  }));
  try {
    const result = await postJson("/api/pipeline/settings", {
      steps: normalized,
      migrate_leads: migrate,
    });
    await applyMutationPayload(result);
    const n = result.migrated_leads || 0;
    showToast(n
      ? `Saved · moved ${n} prospect${n === 1 ? "" : "s"} off removed steps`
      : "Pipeline steps saved.");
    render();
  } catch (error) {
    showToast(error.message || "Could not save pipeline.", true);
  }
}

export function bindPipelineEditor() {
  if (editorBound) return;
  editorBound = true;
  byId("pipelineAddStepButton")?.addEventListener("click", () => {
    const next = rowsFromEditor();
    next.push({ key: "", label: "", wait_hours: 36 });
    renderEditorRows(next);
  });
  byId("pipelineSaveStepsButton")?.addEventListener("click", () => savePipelineSteps());
}
