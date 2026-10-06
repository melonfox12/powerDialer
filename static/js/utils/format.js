const vocabulary = JSON.parse(document.getElementById("vocabulary").textContent);
export const STATUS_STYLES = Object.fromEntries(vocabulary.statuses.map((status) => [status.key, {
  label: status.label,
  color: status.color,
  className: status.className,
}]));
export const STATUS_LABELS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.label]));
export const STATUS_COLOR_VARS = Object.fromEntries(Object.entries(STATUS_STYLES).map(([status, style]) => [status, style.color]));
export const STATUS_KEYS = vocabulary.statuses.map((status) => status.key);
export const TIMEZONE_NAMES = vocabulary.timezones;
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

export function formatMinutes(totalSeconds) {
  const minutes = Math.round((totalSeconds || 0) / 60);
  return `${minutes}m`;
}

export function dayLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return dateStr.slice(5);
  return date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
}
