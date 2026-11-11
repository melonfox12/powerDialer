import { S, state } from "./state.js";

const vocabulary = JSON.parse(document.getElementById("vocabulary").textContent);

const HUMAN_DIALER_PANEL_ID = "dialerTabPanel";

/** Human Dialer tab root (`#dialerTabPanel`). AI Dialer uses its own markup under `#aiDialerAgentTabPanel`. */
export function humanDialerPanel() {
  return document.getElementById(HUMAN_DIALER_PANEL_ID);
}

/** @deprecated Use {@link humanDialerPanel}. */
export function dialerWorkspacePanel() {
  return humanDialerPanel();
}

/** Control inside the human dialer panel by id or `data-dialer-ref`. */
export function dialerEl(elementId) {
  const panel = humanDialerPanel();
  if (!panel || !elementId) return null;
  const byDomId = panel.querySelector(`#${CSS.escape(elementId)}`);
  if (byDomId) return byDomId;
  return panel.querySelector(`[data-dialer-ref="${elementId}"]`);
}

export function dialerById(elementId) {
  return dialerEl(elementId);
}

/** Single-element list for legacy `for (const node of dialerEls(...))` loops. */
export function dialerEls(elementId) {
  const el = dialerEl(elementId);
  return el ? [el] : [];
}

export function setDialerText(elementId, value) {
  const node = dialerEl(elementId);
  if (node) node.textContent = value;
}
export const MARKETING_TOUCHES_FIELD = vocabulary.marketingTouchesField || "Marketing touches";
export const STATUS_STYLES = Object.fromEntries(vocabulary.statuses.map((status) => [status.key, {
  label: status.label,
  color: status.color,
  className: status.className,
}]));
export const STATUS_LABELS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.label]));
export const STATUS_COLOR_VARS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.color]));
export const STATUS_KEYS = vocabulary.statuses.map((status) => status.key);
// Mirrors shared/vocabulary.py when the page was served before crmStatusKeys was added.
const FALLBACK_CRM_STATUS_KEYS = [
  "new",
  "dialed",
  "contact_engaged",
  "qualified",
  "booked",
  "proposal_sent",
  "closed",
];
const FALLBACK_CRM_STATUS_LABELS = {
  new: "New",
  dialed: "Dialed",
  contact_engaged: "Contact (engaged)",
  qualified: "Qualified",
  booked: "Booked",
  proposal_sent: "Proposal sent",
  closed: "Closed",
};
export const CRM_STATUS_KEYS = Array.isArray(vocabulary.crmStatusKeys) && vocabulary.crmStatusKeys.length
  ? vocabulary.crmStatusKeys
  : FALLBACK_CRM_STATUS_KEYS;
export const AGENT_USE_STATUS = vocabulary.agentUseStatus || "agent_use";
export const USER_SELECTABLE_CRM_STATUS_KEYS = Array.isArray(vocabulary.userSelectableCrmStatusKeys)
  && vocabulary.userSelectableCrmStatusKeys.length
  ? vocabulary.userSelectableCrmStatusKeys
  : CRM_STATUS_KEYS.filter((key) => key !== AGENT_USE_STATUS);
export const CRM_STATUS_LABELS = vocabulary.crmStatusLabels ?? FALLBACK_CRM_STATUS_LABELS;
const FALLBACK_NEVER_DIAL_STATUSES = ["booked", "proposal_sent", "closed"];
export const NEVER_DIAL_STATUSES = Array.isArray(vocabulary.neverDialStatuses) && vocabulary.neverDialStatuses.length
  ? vocabulary.neverDialStatuses
  : FALLBACK_NEVER_DIAL_STATUSES;
const FALLBACK_DIAL_POOL_STATUSES = ["new", "contact_engaged"];
const FALLBACK_DIAL_POOL_STATUS_LABELS = { new: "New", contact_engaged: "Contact (engaged)" };
export const DIAL_POOL_STATUSES = Array.isArray(vocabulary.dialPoolStatuses) && vocabulary.dialPoolStatuses.length
  ? vocabulary.dialPoolStatuses
  : FALLBACK_DIAL_POOL_STATUSES;
export const DIAL_POOL_STATUS_LABELS = vocabulary.dialPoolStatusLabels ?? FALLBACK_DIAL_POOL_STATUS_LABELS;
export const DEFAULT_DIAL_POOL_STATUS = vocabulary.defaultDialPoolStatus || "new";
const FALLBACK_DIAL_BUSINESS_TYPE_OPTIONS = [
  { key: "pest control", label: "Pest control" },
  { key: "hvac", label: "HVAC" },
];
export const DIAL_BUSINESS_TYPE_OPTIONS = Array.isArray(vocabulary.dialBusinessTypeOptions)
  && vocabulary.dialBusinessTypeOptions.length
  ? vocabulary.dialBusinessTypeOptions
  : FALLBACK_DIAL_BUSINESS_TYPE_OPTIONS;
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
// A prospect in a never-dial status cannot go back to "new" or "dialed".
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

const FALLBACK_PIPELINE_STEPS = [
  { key: "dialed", label: "Dialed", wait_hours: 0 },
  { key: "call_1", label: "Contacted (engaged)", wait_hours: 0 },
  { key: "email_1", label: "Email 1", wait_hours: 36 },
  { key: "linkedin_add", label: "LinkedIn add request", wait_hours: 36 },
  { key: "call_2", label: "Call 2", wait_hours: 36 },
  { key: "email_2", label: "Email 2", wait_hours: 36 },
  { key: "linkedin_message", label: "LinkedIn message", wait_hours: 36 },
  { key: "call_3", label: "Call 3", wait_hours: 36 },
  { key: "email_3", label: "Email 3", wait_hours: 36 },
  { key: "any_channel", label: "Any channel (every 60–90 days)", wait_hours: 75 * 24 },
];
const VOCAB_PIPELINE_STEPS = Array.isArray(vocabulary.pipelineSteps) && vocabulary.pipelineSteps.length
  ? vocabulary.pipelineSteps
  : FALLBACK_PIPELINE_STEPS;

let _pipelineRuntimeSteps = VOCAB_PIPELINE_STEPS.map((item) => ({ ...item }));

function rebuildPipelineWaitMap() {
  return Object.fromEntries(_pipelineRuntimeSteps.map((item) => [item.key, item.wait_hours]));
}

let PIPELINE_WAIT_HOURS = rebuildPipelineWaitMap();

export function getPipelineSteps() {
  return _pipelineRuntimeSteps;
}

export function getPipelineStepKeys() {
  return _pipelineRuntimeSteps.map((item) => item.key);
}

export function setPipelineRuntimeSteps(steps) {
  if (!Array.isArray(steps) || steps.length < 2) return;
  _pipelineRuntimeSteps = steps.map((item) => ({
    key: String(item.key),
    label: String(item.label),
    wait_hours: Number(item.wait_hours) || 0,
  }));
  PIPELINE_WAIT_HOURS = rebuildPipelineWaitMap();
}

/** Initial boot: vocabulary only; GET /api/leads replaces with server steps when available. */
export const PIPELINE_STEPS = VOCAB_PIPELINE_STEPS;
export const PIPELINE_STEP_KEYS = VOCAB_PIPELINE_STEPS.map((item) => item.key);
export const PIPELINE_FIRST_STEP = vocabulary.pipelineFirstStep || PIPELINE_STEP_KEYS[0] || "dialed";
export const PIPELINE_DIALED_STEP = vocabulary.pipelineDialedStep || "dialed";
export const PIPELINE_SEND_INFO_STEP = vocabulary.pipelineSendInfoStep || "call_1";
export const PIPELINE_LOCKED_STEP_KEYS = [PIPELINE_DIALED_STEP, PIPELINE_SEND_INFO_STEP];

const PIPELINE_STEP_KEY_RE = /^[a-z][a-z0-9_]{0,62}$/;
const MAX_PIPELINE_STEP_KEY_LEN = 63;

/** Turn free text into a storage key (matches shared.pipeline_config.normalize_pipeline_step_key). */
export function formatPipelineStepKey(raw) {
  const s = String(raw ?? "").trim().toLowerCase();
  const parts = [];
  let buf = "";
  for (const ch of s) {
    if ((ch >= "a" && ch <= "z") || (ch >= "0" && ch <= "9")) {
      buf += ch;
    } else if (buf) {
      parts.push(buf);
      buf = "";
    }
  }
  if (buf) parts.push(buf);
  let key = parts.join("_").replace(/^_+|_+$/g, "");
  if (!key) return "";
  if (/^\d/.test(key)) key = `step_${key}`;
  if (key.length > MAX_PIPELINE_STEP_KEY_LEN) {
    key = key.slice(0, MAX_PIPELINE_STEP_KEY_LEN).replace(/_+$/g, "");
  }
  if (!key || !/^[a-z]/.test(key)) return "";
  return PIPELINE_STEP_KEY_RE.test(key) ? key : "";
}
const FALLBACK_PIPELINE_CRM_STATUS_KEYS = [];
export const PIPELINE_CRM_STATUS_KEYS = Array.isArray(vocabulary.pipelineCrmStatusKeys)
  && vocabulary.pipelineCrmStatusKeys.length
  ? vocabulary.pipelineCrmStatusKeys
  : FALLBACK_PIPELINE_CRM_STATUS_KEYS;

export function pipelineWaitHours(stepKey) {
  const k = String(stepKey || "");
  if (PIPELINE_WAIT_HOURS[k] !== undefined) return PIPELINE_WAIT_HOURS[k];
  return PIPELINE_WAIT_HOURS[PIPELINE_FIRST_STEP] ?? 36;
}

export function pipelineReadyAt(stepKey, enteredAtIso) {
  const entered = Date.parse(enteredAtIso || "");
  if (Number.isNaN(entered)) return "";
  const ready = entered + pipelineWaitHours(stepKey) * 3600 * 1000;
  return new Date(ready).toISOString();
}

export function pipelineStepReady(stepKey, enteredAtIso, now = Date.now()) {
  if (stepKey === PIPELINE_SEND_INFO_STEP || stepKey === PIPELINE_DIALED_STEP) return true;
  const due = Date.parse(pipelineReadyAt(stepKey, enteredAtIso));
  return !Number.isNaN(due) && now >= due;
}

export function pipelineCountdown(stepKey, enteredAtIso, now = Date.now()) {
  const readyAt = pipelineReadyAt(stepKey, enteredAtIso);
  const due = Date.parse(readyAt);
  if (Number.isNaN(due)) return "";
  if (now >= due) return "Ready for next step";
  const totalSeconds = Math.ceil((due - now) / 1000);
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  if (days > 0) return `Next in ${days}d ${hours}h`;
  if (hours > 0) return `Next in ${hours}h ${minutes}m`;
  return `Next in ${minutes}m`;
}

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
  if (value === "dialed" && lead?.status === "dialed" && lead.scheduled_until) {
    return callbackStatusText(lead);
  }
  return CRM_STATUS_LABELS[value] || STATUS_LABELS[value] || value;
}

export function agentUseStatusText(lead) {
  const fields = lead?.fields || {};
  const name = String(lead?.agent_reserved_name || fields.agent_reserved_name || "").trim();
  return name ? `Agent ${name} use` : (CRM_STATUS_LABELS[AGENT_USE_STATUS] || "Agent use");
}

export function callbackStatusText(lead, now = Date.now()) {
  if (lead?.status === AGENT_USE_STATUS) return agentUseStatusText(lead);
  const label = STATUS_LABELS[lead?.status] || "New";
  if (lead?.status !== "dialed" || !lead.scheduled_until) return label;
  const countdown = callbackCountdown(lead.scheduled_until, now);
  return countdown ? `${label} ${countdown}` : label;
}

export function markCallback(node, lead) {
  if (lead?.status === "dialed" && lead.scheduled_until) {
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
  if (currentStatus === AGENT_USE_STATUS) {
    select.disabled = true;
    const locked = document.createElement("option");
    locked.value = AGENT_USE_STATUS;
    locked.textContent = agentUseStatusText(lead);
    locked.selected = true;
    select.append(locked);
    bindCrmStatusSelectMenu(select);
    return select;
  }
  if (!CRM_STATUS_KEYS.includes(currentStatus)) {
    const current = document.createElement("option");
    current.value = currentStatus;
    current.textContent = STATUS_LABELS[currentStatus] || currentStatus;
    current.selected = true;
    current.disabled = true;
    select.append(current);
  }
  const ghostAgent = document.createElement("option");
  ghostAgent.value = AGENT_USE_STATUS;
  ghostAgent.textContent = CRM_STATUS_LABELS[AGENT_USE_STATUS] || "Agent use";
  ghostAgent.disabled = true;
  select.append(ghostAgent);
  for (const value of USER_SELECTABLE_CRM_STATUS_KEYS) {
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
    pill.dataset.callbackPrefix = `${STATUS_LABELS.dialed || "Dialed"} `;
  }
  parent.append(pill);
  return pill;
}

export function startStatusClock() {
  const tick = () => {
    const now = Date.now();
    if (document.querySelector("[data-pipeline-timer]")) {
      import("../features/pipeline.js").then((module) => module.tickPipelineTimers()).catch(() => {});
    }
    for (const node of document.querySelectorAll("[data-callback-until]")) {
      const countdown = callbackCountdown(node.dataset.callbackUntil, now);
      const text = `${node.dataset.callbackPrefix || "Dialed "}${countdown}`;
      if (node.tagName === "SELECT") {
        if (node.dataset.statusMenuOpen) continue;
        const option = node.querySelector('option[value="dialed"]');
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
