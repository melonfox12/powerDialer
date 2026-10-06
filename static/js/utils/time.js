import { TIMEZONE_NAMES } from "./format.js";

export function localDateTimeParts(date, timezoneName) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezoneName,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).formatToParts(date);
  return Object.fromEntries(parts.filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
}

export function nextBusinessCallback(lead) {
  const timeZone = timezoneFor(lead.timezone);
  const today = localDateTimeParts(new Date(), timeZone);
  const tomorrow = new Date(Date.UTC(Number(today.year), Number(today.month) - 1, Number(today.day) + 1));
  const local = {
    year: String(tomorrow.getUTCFullYear()),
    month: String(tomorrow.getUTCMonth() + 1).padStart(2, "0"),
    day: String(tomorrow.getUTCDate()).padStart(2, "0"),
  };
  local.hour = "09";
  local.minute = "00";
  return `${local.year}-${local.month}-${local.day}T${local.hour}:${local.minute}`;
}

export function timezoneFor(name) {
  return TIMEZONE_NAMES[name] || name || Intl.DateTimeFormat().resolvedOptions().timeZone;
}

export function localDateTimeToUtc(value, timezoneName) {
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})$/.exec(value);
  if (!match) throw new Error("Choose a valid callback date and time.");
  const desired = Date.UTC(...[Number(match[1]), Number(match[2]) - 1, Number(match[3]), Number(match[4]), Number(match[5])]);
  let candidate = desired;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const parts = localDateTimeParts(new Date(candidate), timezoneName);
    const observed = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), Number(parts.hour), Number(parts.minute));
    candidate += desired - observed;
  }
  return new Date(candidate).toISOString();
}
