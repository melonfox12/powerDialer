import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

let columnSort = null;

export function currentColumnSort() {
  return columnSort;
}

export function setColumnSort(key, direction) {
  columnSort = { key, direction };
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
  const standard = /^(name|full name|contact|first name|last name|business|company|organization|organisation|state|city|phone(?: number| e\.?164)?|mobile|cell|telephone|time\s?zone|tz|call.?status|status)$/i;
  for (const lead of state.leads) {
    for (const key of Object.keys(lead.fields || {})) {
      if (!standard.test(key) && !columns.includes(key)) columns.push(key);
    }
  }
  return columns;
}

export function filteredLeads() {
  const query = byId("searchInput").value.trim().toLocaleLowerCase();
  const filter = byId("statusFilter").value;
  const leads = state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (!query) return true;
    const values = [lead.name, lead.business, locationText(lead, "state"), locationText(lead, "city"), lead.phone, lead.status, ...Object.values(lead.fields || {})];
    return values.some((value) => String(value || "").toLocaleLowerCase().includes(query));
  });
  if (!columnSort) return leads;
  const direction = columnSort.direction === "desc" ? -1 : 1;
  return leads.sort((left, right) => {
    const leftValue = sortText(left);
    const rightValue = sortText(right);
    if (!leftValue && !rightValue) return tieBreak(left, right);
    if (!leftValue) return 1;
    if (!rightValue) return -1;
    const compared = leftValue.localeCompare(rightValue, undefined, { sensitivity: "base" });
    return compared ? compared * direction : tieBreak(left, right);
  });
}

function sortText(lead) {
  if (columnSort.key === "business") return String(lead.business || "").trim();
  return locationText(lead, columnSort.key);
}

function tieBreak(left, right) {
  return String(left.name || "").localeCompare(String(right.name || ""), undefined, { sensitivity: "base" });
}

export function crmTableSignature() {
  return JSON.stringify([
    columnSort,
    state.pending_outcome?.id || null,
    state.leads.map((lead) => [
      lead.id,
      lead.name,
      lead.business,
      locationText(lead, "state"),
      locationText(lead, "city"),
      lead.phone,
      lead.timezone,
      lead.status,
      lead.scheduled_until,
      lead.fields,
      lead.transcript?.length || 0,
    ]),
  ]);
}
