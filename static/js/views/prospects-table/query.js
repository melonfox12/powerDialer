import { S, selectedLeadIds, state } from "../../store/state.js";
import { byId } from "../../utils/format.js";

export function importedColumns() {
  const columns = [];
  const standard = /^(name|full name|contact|first name|last name|business|company|organization|organisation|phone(?: number| e\.?164)?|mobile|cell|telephone|time\s?zone|tz|call.?status|status)$/i;
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
  return state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (!query) return true;
    const values = [lead.name, lead.business, lead.phone, lead.status, ...Object.values(lead.fields || {})];
    return values.some((value) => String(value || "").toLocaleLowerCase().includes(query));
  });
}

export function crmTableSignature() {
  return JSON.stringify([
    state.pending_outcome?.id || null,
    state.leads.map((lead) => [
      lead.id,
      lead.name,
      lead.business,
      lead.phone,
      lead.timezone,
      lead.status,
      lead.scheduled_until,
      lead.fields,
      lead.transcript?.length || 0,
    ]),
  ]);
}
