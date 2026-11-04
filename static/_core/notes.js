import { postJson } from "./api.js";
import { byId } from "./format.js";
import { applyMutationPayload } from "./sync-state.js";
import { showToast } from "./notify.js";

export const NOTES_FIELD = "Notes";

export function leadNotes(lead) {
  for (const [name, value] of Object.entries(lead?.fields || {})) {
    if (name.trim().toLowerCase() === "notes") return String(value || "").trim();
  }
  return "";
}

export function notesLeadLabel(lead) {
  return lead?.name || lead?.business || lead?.phone || "Prospect";
}

export async function persistLeadNotes(lead, text, input) {
  const trimmed = String(text ?? "").trim();
  const payload = { fields: { [NOTES_FIELD]: trimmed } };
  if (input) input.disabled = true;
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/fields`, payload);
    await applyMutationPayload(result);
    if (input?.isConnected) {
      input.dataset.savedValue = trimmed;
      input.value = trimmed;
      input.disabled = false;
    }
    return true;
  } catch (error) {
    if (input?.isConnected) input.disabled = false;
    showToast(error?.message || "Could not save notes.", true);
    return false;
  }
}

function bindNotesEditor(textarea, lead) {
  const label = notesLeadLabel(lead);
  textarea.className = "notes-editor cell-editor";
  textarea.value = leadNotes(lead);
  textarea.dataset.savedValue = textarea.value;
  textarea.placeholder = "Add notes…";
  textarea.setAttribute("aria-label", `Notes for ${label}`);
  textarea.rows = textarea.classList.contains("notes-editor-compact") ? 2 : 3;
  textarea.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      textarea.value = textarea.dataset.savedValue;
      event.preventDefault();
      textarea.blur();
    }
  });
  textarea.addEventListener("blur", () => {
    const trimmed = textarea.value.trim();
    if (trimmed === textarea.dataset.savedValue) {
      textarea.value = textarea.dataset.savedValue;
      document.dispatchEvent(new CustomEvent("prospect-field-blur"));
      return;
    }
    document.dispatchEvent(new CustomEvent("prospect-field", {
      detail: {
        lead,
        field: "fields",
        extra: NOTES_FIELD,
        value: trimmed,
        previous: textarea.dataset.savedValue,
        input: textarea,
      },
    }));
  });
}

export function createNotesTextarea(lead, { compact = false } = {}) {
  const textarea = document.createElement("textarea");
  if (compact) textarea.classList.add("notes-editor-compact");
  bindNotesEditor(textarea, lead);
  return textarea;
}

export function notesEditorFocused(container) {
  const root = typeof container === "string" ? byId(container) : container;
  const active = document.activeElement;
  return active instanceof HTMLElement && active.classList.contains("notes-editor") && root?.contains(active);
}

export function appendNotesCell(row, lead, { compact = false } = {}) {
  const cell = document.createElement("td");
  cell.className = "notes-cell";
  cell.append(createNotesTextarea(lead, { compact }));
  row.append(cell);
  return cell;
}
