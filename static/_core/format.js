import { state } from "./state.js";

const vocabulary = JSON.parse(document.getElementById("vocabulary").textContent);
export const STATUS_STYLES = Object.fromEntries(vocabulary.statuses.map((status) => [status.key, {
  label: status.label,
  color: status.color,
  className: status.className,
}]));
export const STATUS_LABELS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.label]));
export const STATUS_COLOR_VARS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.color]));
export const STATUS_KEYS = vocabulary.statuses.map((status) => status.key);
// Mirrors shared/vocabulary.py when the page was served before crmStatusKeys was added.
const FALLBACK_CRM_STATUS_KEYS = ["new", "call", "send_info", "booked", "disqualified", "no_answer_disqualified"];
const FALLBACK_CRM_STATUS_LABELS = {
  new: "New",
  call: "Callback",
  send_info: "Send info",
  booked: "Booked",
  disqualified: "Disqualified",
  no_answer_disqualified: "No answer (disqualified)",
};
export const CRM_STATUS_KEYS = Array.isArray(vocabulary.crmStatusKeys) && vocabulary.crmStatusKeys.length
  ? vocabulary.crmStatusKeys
  : FALLBACK_CRM_STATUS_KEYS;
export const CRM_STATUS_LABELS = vocabulary.crmStatusLabels ?? FALLBACK_CRM_STATUS_LABELS;
const FALLBACK_NEVER_DIAL_STATUSES = ["booked", "disqualified", "no_answer_disqualified"];
export const NEVER_DIAL_STATUSES = Array.isArray(vocabulary.neverDialStatuses) && vocabulary.neverDialStatuses.length
  ? vocabulary.neverDialStatuses
  : FALLBACK_NEVER_DIAL_STATUSES;
const FALLBACK_DIAL_POOL_STATUSES = ["new", "send_info"];
const FALLBACK_DIAL_POOL_STATUS_LABELS = { new: "New", send_info: "Send info" };
export const DIAL_POOL_STATUSES = Array.isArray(vocabulary.dialPoolStatuses) && vocabulary.dialPoolStatuses.length
  ? vocabulary.dialPoolStatuses
  : FALLBACK_DIAL_POOL_STATUSES;
export const DIAL_POOL_STATUS_LABELS = vocabulary.dialPoolStatusLabels ?? FALLBACK_DIAL_POOL_STATUS_LABELS;
export const DEFAULT_DIAL_POOL_STATUS = vocabulary.defaultDialPoolStatus || "new";
const FALLBACK_CALLER_ID_GROUPS = [
  { key: "eastern", label: "Eastern" },
  { key: "central", label: "Central" },
  { key: "mountain", label: "Mountain" },
  { key: "pacific", label: "Pacific" },
];
export const CALLER_ID_GROUPS = Array.isArray(vocabulary.callerIdGroups) && vocabulary.callerIdGroups.length
  ? vocabulary.callerIdGroups
  : FALLBACK_CALLER_ID_GROUPS;
export const DEFAULT_CALLER_ID_GROUP = vocabulary.defaultCallerIdGroup || "eastern";
export const CALLBACK_STATUS_HOURS = vocabulary.callbackStatusHours ?? 2;
// A prospect in a never-dial status cannot go back to "new" or "call".
export const leavesQueueForGood = (lead, status) => (
  NEVER_DIAL_STATUSES.includes(lead?.status) && !NEVER_DIAL_STATUSES.includes(status)
);
export const TIMEZONE_NAMES = vocabulary.timezones;
export const CALL_OUTCOMES = vocabulary.callOutcomes;
export const CALL_OUTCOME_LABELS = Object.fromEntries(CALL_OUTCOMES.map((item) => [item.key, item.label]));
export const PERFORMANCE_RANGES = vocabulary.performanceRanges;
export const DEFAULT_PERFORMANCE_RANGE = vocabulary.defaultPerformanceRange;
export const CONVERSATION_MIN_SECONDS = vocabulary.conversationMinSeconds;
export const HEATMAP_UNLOCK_DIALS = vocabulary.heatmapUnlockDials;
export const HEATMAP_MIN_BUCKET_DIALS = vocabulary.heatmapMinBucketDials;

export function fillTimezoneSelect(select, selected = "Unknown") {
  const current = String(selected || "Unknown");
  const names = ["Unknown", ...Object.keys(TIMEZONE_NAMES)];
  if (!names.includes(current)) names.push(current);
  select.replaceChildren();
  for (const name of names) {
    const option = document.createElement("option");
    option.value = name;
    option.textContent = name;
    select.append(option);
  }
  select.value = current;
}
export const SECRET_INPUTS = vocabulary.secretInputs.map((item) => [item.id, item.label]);

export const byId = (id) => document.getElementById(id);
export function setText(id, value) {
  byId(id).textContent = value;
}

export function initials(name) {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  return words.length > 1 ? `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase() : (words[0] || "?").slice(0, 2).toUpperCase();
}

export function statusDate(lead) {
  if (!lead.scheduled_until) return "";
  const due = new Date(lead.scheduled_until);
  if (Number.isNaN(due.getTime())) return "";
  return due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function callbackCountdown(until, now = Date.now()) {
  const due = new Date(until || "").getTime();
  if (Number.isNaN(due)) return "";
  const total = Math.max(0, Math.ceil((due - now) / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

export function crmStatusOptionText(value, lead) {
  if (value === "call" && lead?.status === "call" && lead.scheduled_until) {
    return callbackStatusText(lead);
  }
  return CRM_STATUS_LABELS[value] || STATUS_LABELS[value] || value;
}

export function callbackStatusText(lead, now = Date.now()) {
  const label = STATUS_LABELS[lead?.status] || "New";
  if (lead?.status !== "call" || !lead.scheduled_until) return label;
  const countdown = callbackCountdown(lead.scheduled_until, now);
  return countdown ? `${label} ${countdown}` : label;
}

export function markCallback(node, lead) {
  if (lead?.status === "call" && lead.scheduled_until) {
    node.dataset.callbackUntil = lead.scheduled_until;
    return true;
  }
  delete node.dataset.callbackUntil;
  return false;
}

export function crmStatusMenuOpen(container) {
  const open = document.querySelector(".status-select[data-status-menu-open]");
  if (!open) return false;
  if (!container) return true;
  return container.contains(open);
}

function bindCrmStatusSelectMenu(select) {
  const open = () => {
    select.dataset.statusMenuOpen = "true";
  };
  const close = () => {
    if (!select.dataset.statusMenuOpen) return;
    delete select.dataset.statusMenuOpen;
    document.dispatchEvent(new CustomEvent("crm-status-menu-close", { detail: { select } }));
  };
  select.addEventListener("pointerdown", open);
  select.addEventListener("keydown", (event) => {
    if (["ArrowDown", "ArrowUp", "Enter", " ", "Home", "End"].includes(event.key)) open();
    if (event.key === "Escape") close();
  });
  select.addEventListener("blur", close);
}

/** Editable CRM status menu; dispatches `prospect-status` on change (handled in prospects records). */
export function createCrmStatusSelect(lead) {
  const select = document.createElement("select");
  const currentStatus = lead?.status || "new";
  select.className = `status-select status-${STATUS_STYLES[currentStatus]?.className || "neutral"}`;
  const name = lead?.name || lead?.phone || lead?.business || "prospect";
  select.setAttribute("aria-label", `Call status for ${name}`);
  if (!CRM_STATUS_KEYS.includes(currentStatus)) {
    const current = document.createElement("option");
    current.value = currentStatus;
    current.textContent = STATUS_LABELS[currentStatus] || currentStatus;
    current.selected = true;
    current.disabled = true;
    select.append(current);
  }
  for (const value of CRM_STATUS_KEYS) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = crmStatusOptionText(value, lead);
    option.selected = currentStatus === value;
    if (value === "new" && state.pending_outcome?.id === lead.id) option.disabled = true;
    if (leavesQueueForGood(lead, value)) option.disabled = true;
    select.append(option);
  }
  select.addEventListener("change", () => {
    const next = String(select.value || "").trim();
    if (!next || !CRM_STATUS_KEYS.includes(next)) {
      select.value = currentStatus;
      return;
    }
    const current = state.leads.find((item) => item.id === lead.id) || lead;
    document.dispatchEvent(new CustomEvent("prospect-status", {
      detail: { lead: current, status: next, select },
    }));
  });
  markCallback(select, lead);
  bindCrmStatusSelectMenu(select);
  return select;
}

/** Read-only CRM status pill; use markCallback so the global status clock can refresh callbacks. */
export function appendStatusPill(parent, lead) {
  const currentStatus = lead?.status || "new";
  const pill = document.createElement("span");
  pill.className = `status-select status-${STATUS_STYLES[currentStatus]?.className || "neutral"}`;
  pill.setAttribute("aria-label", `Status: ${STATUS_LABELS[currentStatus] || "New"}`);
  pill.textContent = callbackStatusText(lead);
  if (markCallback(pill, lead)) {
    pill.dataset.callbackPrefix = `${STATUS_LABELS.call} `;
  }
  parent.append(pill);
  return pill;
}

export function startStatusClock() {
  const tick = () => {
    const now = Date.now();
    for (const node of document.querySelectorAll("[data-callback-until]")) {
      const countdown = callbackCountdown(node.dataset.callbackUntil, now);
      const text = `${node.dataset.callbackPrefix || "Callback "}${countdown}`;
      if (node.tagName === "SELECT") {
        if (node.dataset.statusMenuOpen) continue;
        const option = node.querySelector('option[value="call"]');
        if (option) option.textContent = text;
      } else {
        node.textContent = text;
      }
    }
  };
  tick();
  setInterval(tick, 1000);
}

export function formatMinutes(totalSeconds) {
  const minutes = Math.round((totalSeconds || 0) / 60);
  return `${minutes}m`;
}

export function dayLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return dateStr.slice(5);
  return date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
}

// A 0 to 1 ratio as a percent. A missing ratio (nothing to divide by) is a dash, never NaN.
export function formatRate(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  const percent = Math.round(value * 1000) / 10;
  if (percent === 0) return "0%";
  return `${percent < 10 ? percent.toFixed(1) : Math.round(percent)}%`;
}

export function formatDuration(totalSeconds) {
  if (typeof totalSeconds !== "number" || !Number.isFinite(totalSeconds)) return "—";
  const seconds = Math.round(totalSeconds);
  const minutes = Math.floor(seconds / 60);
  return minutes ? `${minutes}m ${String(seconds % 60).padStart(2, "0")}s` : `${seconds}s`;
}
