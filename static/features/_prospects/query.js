import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export const LEAD_COLUMNS = [
  { label: "Business Type", key: "business_type", kind: "text" },
  { label: "Prospect", key: "name", kind: "text" },
  { label: "Company", key: "business", kind: "text" },
  { label: "State", key: "state", kind: "text" },
  { label: "City", key: "city", kind: "text" },
  { label: "Phone Number", key: "phone", kind: "text" },
  { label: "Timezone", key: "timezone", kind: "text" },
  { label: "Total Reviews", key: "review_count", kind: "number" },
  { label: "Call status", key: "status", kind: "text" },
  { label: "Reviews (Last 30 Days)", key: "reviews_last_30_days", kind: "number" },
  { label: "Days Since Last Review", key: "days_since_last_review", kind: "number" },
  { label: "30-Day %", key: "review_pct_30_days", kind: "number" },
  { label: "Recency Source", key: "recency_source", kind: "text" },
];

export const TRAILING_COLUMNS = [
  { label: "Call transcript", key: "transcript", kind: "number" },
];

let columnSort = { key: "review_pct_30_days", direction: "desc", kind: "number" };

export function currentColumnSort() {
  return columnSort;
}

export function setColumnSort(key, direction) {
  columnSort = { key, direction, kind: columnKind(key) };
}

export function toggleColumnSort(key) {
  const kind = columnKind(key);
  if (columnSort?.key === key) {
    columnSort = { key, kind, direction: columnSort.direction === "desc" ? "asc" : "desc" };
    return;
  }
  columnSort = { key, kind, direction: kind === "number" ? "desc" : "asc" };
}

export function locationText(lead, key) {
  const direct = String(lead?.[key] || "").trim();
  if (direct) return direct;
  for (const [name, value] of Object.entries(lead?.fields || {})) {
    if (name.trim().toLowerCase() === key) return String(value || "").trim();
  }
  return "";
}

export function importedColumns() {
  const columns = [];
  const standard = /^(name|full name|contact|first name|last name|prospect|business type|industry|business|company|organization|organisation|state|city|phone(?: number| e\.?164)?|mobile|cell|telephone|time\s?zone|tz|call.?status|status|total reviews|reviews \(last 30 days\)|days since last review|30-day %|recency source|fit)$/i;
  for (const lead of state.leads) {
    for (const key of Object.keys(lead.fields || {})) {
      if (!standard.test(key) && !columns.includes(key)) columns.push(key);
    }
  }
  return columns;
}

export function syncStateFilter() {
  const select = byId("stateFilter");
  if (!select) return;
  const current = select.value;
  const states = [...new Set(state.leads.map((lead) => locationText(lead, "state")).filter(Boolean))];
  states.sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));
  const wanted = ["", ...states];
  const existing = [...select.options].map((option) => option.value);
  if (existing.join("\0") === wanted.join("\0")) return;
  select.replaceChildren();
  const all = document.createElement("option");
  all.value = "";
  all.textContent = "All states";
  select.append(all);
  for (const code of states) {
    const option = document.createElement("option");
    option.value = code;
    option.textContent = code;
    select.append(option);
  }
  select.value = wanted.includes(current) ? current : "";
}

export function filteredLeads() {
  const query = byId("searchInput").value.trim().toLocaleLowerCase();
  const filter = byId("statusFilter").value;
  const stateFilter = (byId("stateFilter")?.value || "").trim().toUpperCase();
  const minTotal = bound("minTotalReviews");
  const maxTotal = bound("maxTotalReviews");
  const minRecent = bound("minRecentReviews");
  const leads = state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (stateFilter && locationText(lead, "state").trim().toUpperCase() !== stateFilter) return false;
    const total = numberOrNull(lead.review_count);
    const recent = numberOrNull(lead.reviews_last_30_days);
    if (minTotal != null && (total == null || total < minTotal)) return false;
    if (maxTotal != null && (total == null || total > maxTotal)) return false;
    if (minRecent != null && (recent == null || recent < minRecent)) return false;
    if (!query) return true;
    const values = [
      lead.business_type, lead.name, lead.business, locationText(lead, "state"), locationText(lead, "city"),
      lead.phone, lead.timezone, lead.status, lead.recency_source,
      lead.review_count, lead.reviews_last_30_days, lead.days_since_last_review, lead.review_pct_30_days,
      ...Object.values(lead.fields || {}),
    ];
    return values.some((value) => String(value ?? "").toLocaleLowerCase().includes(query));
  });
  if (!columnSort) return leads;
  return leads.sort(compareLeads);
}

export function crmTableSignature() {
  return JSON.stringify([
    columnSort,
    byId("stateFilter")?.value || "",
    byId("minTotalReviews")?.value || "",
    byId("maxTotalReviews")?.value || "",
    byId("minRecentReviews")?.value || "",
    state.pending_outcome?.id || null,
    state.leads.map((lead) => [
      lead.id,
      lead.business_type,
      lead.name,
      lead.business,
      locationText(lead, "state"),
      locationText(lead, "city"),
      lead.phone,
      lead.timezone,
      lead.review_count,
      lead.reviews_last_30_days,
      lead.days_since_last_review,
      lead.review_pct_30_days,
      lead.recency_source,
      lead.status,
      lead.scheduled_until,
      lead.fields,
      lead.transcript?.length || 0,
    ]),
  ]);
}

function columnKind(key) {
  const column = [...LEAD_COLUMNS, ...TRAILING_COLUMNS].find((item) => item.key === key);
  return column?.kind || "text";
}

function bound(id) {
  const raw = byId(id)?.value.trim() ?? "";
  if (raw === "") return null;
  const number = Number(raw);
  return Number.isFinite(number) ? number : null;
}

function numberOrNull(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function compareLeads(left, right) {
  const direction = columnSort.direction === "desc" ? -1 : 1;
  const leftValue = sortValue(left);
  const rightValue = sortValue(right);
  if (leftValue == null && rightValue == null) return tieBreak(left, right);
  if (leftValue == null) return 1;
  if (rightValue == null) return -1;
  if (typeof leftValue === "number" && typeof rightValue === "number") {
    return leftValue === rightValue ? tieBreak(left, right) : (leftValue - rightValue) * direction;
  }
  const compared = String(leftValue).localeCompare(String(rightValue), undefined, { numeric: true, sensitivity: "base" });
  return compared ? compared * direction : tieBreak(left, right);
}

function sortValue(lead) {
  const key = columnSort.key;
  if (columnSort.kind === "number") {
    if (key === "transcript") return lead.transcript?.length || 0;
    return numberOrNull(lead[key]);
  }
  if (key === "state" || key === "city") {
    return locationText(lead, key) || null;
  }
  if (key.startsWith("field:")) {
    return String(lead.fields?.[key.slice(6)] || "").trim() || null;
  }
  return String(lead[key] || "").trim() || null;
}

function tieBreak(left, right) {
  return String(left.name || left.business || "").localeCompare(String(right.name || right.business || ""), undefined, { sensitivity: "base" });
}
