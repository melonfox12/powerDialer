import { postJson } from "./api.js";
import { byId, MARKETING_TOUCHES_FIELD } from "./format.js";
import { applyMutationPayload } from "./sync-state.js";
import { showToast } from "./notify.js";

export const NOTES_FIELD = "Notes";

const TOUCH_KIND_ALIASES = {
  call: "called",
  phone: "called",
  email: "emailed",
  linkedin: "linkedin",
  mail: "mailed",
  mailed: "mailed",
};

function normalizeTouchEntry(item) {
  if (!item) return null;
  if (typeof item === "string") {
    const kind = String(item).trim().toLowerCase();
    const mapped = TOUCH_KIND_ALIASES[kind] || kind;
    return { kind: mapped, at: Date.now() };
  }
  if (typeof item === "object" && item.kind) {
    const raw = String(item.kind).trim().toLowerCase();
    const kind = TOUCH_KIND_ALIASES[raw] || raw;
    const at = Number(item.at);
    return { kind, at: Number.isFinite(at) ? at : Date.now() };
  }
  return null;
}

/** Local noon on yyyy-mm-dd (from `<input type="date">`). Invalid or empty → now. */
export function touchTimestampFromDateInput(value) {
  if (!value || typeof value !== "string") return Date.now();
  const trimmed = value.trim();
  if (!/^\d{4}-\d{2}-\d{2}$/.test(trimmed)) return Date.now();
  const [y, m, d] = trimmed.split("-").map(Number);
  const t = new Date(y, m - 1, d, 12, 0, 0, 0).getTime();
  return Number.isFinite(t) ? t : Date.now();
}

export function leadMarketingTouches(lead) {
  const fields = lead?.fields || {};
  let raw = null;
  for (const [name, value] of Object.entries(fields)) {
    if (String(name).trim().toLowerCase() === MARKETING_TOUCHES_FIELD.toLowerCase()) {
      raw = value;
      break;
    }
  }
  if (raw == null) return [];
  if (Array.isArray(raw)) {
    return raw.map(normalizeTouchEntry).filter(Boolean);
  }
  const text = String(raw).trim();
  if (!text) return [];
  try {
    const parsed = JSON.parse(text);
    if (!Array.isArray(parsed)) return [];
    return parsed.map(normalizeTouchEntry).filter(Boolean);
  } catch {
    return [];
  }
}

const MARKETING_TOUCHES_VALUE_MAX = 480;

function trimTouchesForStorage(touches) {
  let list = Array.isArray(touches) ? [...touches] : [];
  while (list.length > 0 && JSON.stringify(list).length > MARKETING_TOUCHES_VALUE_MAX) {
    list = list.slice(1);
  }
  if (JSON.stringify(list).length > MARKETING_TOUCHES_VALUE_MAX) {
    return null;
  }
  return list;
}

/** Oldest-first for timeline display. */
export function sortedMarketingTouchesChronological(lead) {
  return [...leadMarketingTouches(lead)].sort((a, b) => a.at - b.at);
}

export async function persistMarketingTouches(lead, touches, disableTarget) {
  const stored = trimTouchesForStorage(touches);
  if (stored === null) {
    showToast("Touch history is too long to save. Remove some entries.", true);
    return false;
  }
  const payload = { fields: { [MARKETING_TOUCHES_FIELD]: JSON.stringify(stored) } };
  if (disableTarget) disableTarget.disabled = true;
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/fields`, payload);
    await applyMutationPayload(result);
    return true;
  } catch (error) {
    showToast(error?.message || "Could not save touches.", true);
    return false;
  } finally {
    if (disableTarget?.isConnected) disableTarget.disabled = false;
  }
}

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
