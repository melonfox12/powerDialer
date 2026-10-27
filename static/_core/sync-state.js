import { request } from "./api.js";
import { state } from "./state.js";

/** Merge dialer snapshot fields without wiping cached lead rows. */
export function mergeLiveState(live) {
  if (!live) return;
  const leads = state.leads;
  const pool = state.pool;
  const timezoneGroups = state.timezone_groups;
  const counts = state.counts;
  Object.assign(state, live);
  if (!Object.prototype.hasOwnProperty.call(live, "leads")) state.leads = leads;
  if (!Object.prototype.hasOwnProperty.call(live, "pool")) state.pool = pool;
  if (!Object.prototype.hasOwnProperty.call(live, "timezone_groups")) state.timezone_groups = timezoneGroups;
  if (!Object.prototype.hasOwnProperty.call(live, "counts")) state.counts = counts;
}

export function mergeLeadPatch(leads, patch) {
  if (!patch?.id || !Array.isArray(leads)) return;
  const index = leads.findIndex((lead) => lead.id === patch.id);
  if (index >= 0) leads[index] = patch;
  else leads.push(patch);
}

export function applyLeadsCatalog(catalog) {
  if (!catalog) return;
  state.leads_version = catalog.leads_version;
  state.leads = catalog.leads || [];
  state.archived_dials = catalog.archived_dials || [];
  state.dials_version = catalog.dials_version ?? state.dials_version;
  state.pool = catalog.pool || [];
  state.timezone_groups = catalog.timezone_groups || [];
  state.counts = catalog.counts || state.counts;
}

export async function fetchLeadsCatalog() {
  return request("/api/leads");
}

export async function refreshLeadsIfStale(expectedVersion) {
  if (expectedVersion === undefined || expectedVersion === state.leads_version) {
    if (Array.isArray(state.leads)) return;
  }
  applyLeadsCatalog(await fetchLeadsCatalog());
}

/** After a mutation: merge slim state, patch one lead, reload catalog when CRM revision moved. */
export async function applyMutationPayload(payload) {
  const before = state.leads_version;
  if (payload?.state) mergeLiveState(payload.state);
  if (payload?.lead) mergeLeadPatch(state.leads, payload.lead);
  const after = payload?.state?.leads_version ?? state.leads_version;
  if (!Array.isArray(state.leads) || after !== before) {
    applyLeadsCatalog(await fetchLeadsCatalog());
  }
}

export async function loadAppState() {
  const live = await request("/api/live");
  mergeLiveState(live);
  await refreshLeadsIfStale(live.leads_version);
}
