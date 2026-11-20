import { request } from "./api.js";
import { S, state } from "./state.js";
import { ensurePipelineRuntimeFromCatalog } from "../features/_pipeline/pipeline-steps.js";
import { fieldText, locationText } from "../features/_prospects/query.js";

/** Tabs that need the full CRM catalog (transcripts, call_log, wide fields). */
export const FULL_LEADS_TABS = new Set(["prospects", "pipeline", "workflow"]);

export function needsFullLeadsCatalog(tab = S.dashboardTab) {
  return FULL_LEADS_TABS.has(tab);
}

/** Rows for workflow picker / slim views. */
export function pickerLeads() {
  if (state.leads_full_loaded && Array.isArray(state.leads) && state.leads.length) {
    return state.leads;
  }
  return state.leads_summary || [];
}

export function slimLeadRow(lead) {
  if (!lead?.id) return null;
  const fields = lead.fields || {};
  const businessType =
    String(lead.business_type || "").trim() ||
    fieldText(lead, "Business Type", "business type", "industry", "Industry");
  return {
    id: lead.id,
    name: lead.name || "",
    business: lead.business || "",
    phone: lead.phone || "",
    status: lead.status || "new",
    timezone: lead.timezone || "",
    business_type: businessType,
    state: locationText(lead, "state"),
    scheduled_until: lead.scheduled_until ?? null,
  };
}

/** Merge dialer snapshot fields without wiping cached lead rows. */
export function mergeLiveState(live) {
  if (!live) return;
  const leads = state.leads;
  const leadsSummary = state.leads_summary;
  const leadsFullLoaded = state.leads_full_loaded;
  const pool = state.pool;
  const timezoneGroups = state.timezone_groups;
  const counts = state.counts;
  const pipelineSteps = state.pipeline_steps;
  const pipelineRevision = state.pipeline_revision;
  Object.assign(state, live);
  if (!Object.prototype.hasOwnProperty.call(live, "leads")) state.leads = leads;
  state.leads_summary = leadsSummary;
  state.leads_full_loaded = leadsFullLoaded;
  if (!Object.prototype.hasOwnProperty.call(live, "pool")) state.pool = pool;
  if (!Object.prototype.hasOwnProperty.call(live, "timezone_groups")) state.timezone_groups = timezoneGroups;
  if (!Object.prototype.hasOwnProperty.call(live, "counts")) state.counts = counts;
  if (!Object.prototype.hasOwnProperty.call(live, "pipeline_steps")) state.pipeline_steps = pipelineSteps;
  if (!Object.prototype.hasOwnProperty.call(live, "pipeline_revision")) state.pipeline_revision = pipelineRevision;
  if (live.pipeline_steps?.length) {
    state.pipeline_steps = live.pipeline_steps;
    state.pipeline_revision = live.pipeline_revision ?? state.pipeline_revision;
    ensurePipelineRuntimeFromCatalog(live);
  }
}

export function mergeLeadPatch(leads, patch) {
  if (!patch?.id || !Array.isArray(leads)) return;
  const index = leads.findIndex((lead) => lead.id === patch.id);
  if (index >= 0) leads[index] = patch;
  else leads.push(patch);
}

export function mergeLiveLeadPatches(live) {
  for (const patch of [live?.active_lead, live?.pending_outcome]) {
    if (!patch?.id) continue;
    if (state.leads_full_loaded && Array.isArray(state.leads)) {
      mergeLeadPatch(state.leads, patch);
    }
    const slim = slimLeadRow(patch);
    if (Array.isArray(state.leads_summary) && slim) {
      mergeLeadPatch(state.leads_summary, slim);
    }
  }
}

export function applyLeadsCatalog(catalog) {
  if (!catalog) return;
  state.leads_version = catalog.leads_version;
  state.leads = catalog.leads || [];
  state.leads_full_loaded = true;
  if (Array.isArray(catalog.pipeline_steps) && catalog.pipeline_steps.length) {
    state.pipeline_steps = catalog.pipeline_steps;
    state.pipeline_revision = catalog.pipeline_revision ?? state.pipeline_revision;
    ensurePipelineRuntimeFromCatalog(catalog);
  }
  state.archived_dials = catalog.archived_dials || [];
  state.dials_version = catalog.dials_version ?? state.dials_version;
  state.dial_records = catalog.dial_records || [];
  state.dial_records_version = catalog.dial_records_version ?? state.dial_records_version;
  state.pool = catalog.pool || [];
  state.global_dialer_pool = catalog.global_dialer_pool || catalog.pool || [];
  state.global_dialer_pool_count = state.global_dialer_pool.length;
  state.timezone_groups = catalog.timezone_groups || [];
  state.business_type_options = catalog.business_type_options || [];
  state.counts = catalog.counts || state.counts;
}

export function applyLeadsSummary(catalog) {
  if (!catalog) return;
  state.leads_version = catalog.leads_version;
  state.leads_summary = catalog.leads || [];
  state.leads_full_loaded = false;
  state.counts = catalog.counts || state.counts;
  state.business_type_options = catalog.business_type_options || state.business_type_options;
  if (Array.isArray(catalog.pipeline_steps) && catalog.pipeline_steps.length) {
    state.pipeline_steps = catalog.pipeline_steps;
    state.pipeline_revision = catalog.pipeline_revision ?? state.pipeline_revision;
    ensurePipelineRuntimeFromCatalog(catalog);
  }
}

export async function fetchLeadsCatalog() {
  return request("/api/leads");
}

export async function fetchLeadsSummary() {
  return request("/api/leads/summary");
}

/** One in-flight catalog fetch per mode so refresh + tab switch do not duplicate huge JSON. */
let fullCatalogLoad = null;
let summaryCatalogLoad = null;

function finishCatalogLoad(mode) {
  if (mode === "full") fullCatalogLoad = null;
  else summaryCatalogLoad = null;
}

/** Drop cached lead payloads and cancel in-flight catalog fetches (unload / bfcache). */
export function wipeClientCatalogMemory() {
  fullCatalogLoad = null;
  summaryCatalogLoad = null;
  state.leads = [];
  state.leads_summary = [];
  state.leads_full_loaded = false;
  state.archived_dials = [];
  state.dial_records = [];
  state.pool = [];
  state.global_dialer_pool = [];
  state.global_dialer_pool_count = 0;
}

async function loadFullCatalog() {
  if (fullCatalogLoad) return fullCatalogLoad;
  fullCatalogLoad = fetchLeadsCatalog()
    .then((catalog) => {
      applyLeadsCatalog(catalog);
      state.leads_full_loaded = true;
    })
    .finally(() => finishCatalogLoad("full"));
  return fullCatalogLoad;
}

async function loadSummaryCatalog() {
  if (summaryCatalogLoad) return summaryCatalogLoad;
  summaryCatalogLoad = fetchLeadsSummary()
    .then((catalog) => {
      applyLeadsSummary(catalog);
      state.leads = [];
      state.leads_full_loaded = false;
    })
    .finally(() => finishCatalogLoad("summary"));
  return summaryCatalogLoad;
}

export async function refreshLeadsCatalogForTab() {
  if (needsFullLeadsCatalog()) {
    return loadFullCatalog();
  }
  return loadSummaryCatalog();
}

export function leadsCatalogIsStale(liveVersion) {
  if (liveVersion !== state.leads_version) return true;
  if (needsFullLeadsCatalog()) {
    return !(state.leads_full_loaded && Array.isArray(state.leads));
  }
  return !Array.isArray(state.leads_summary);
}

export async function ensureFullLeadsCatalog() {
  if (
    state.leads_full_loaded &&
    Array.isArray(state.leads) &&
    (state.leads.length > 0 || (state.counts?.total ?? 0) === 0)
  ) {
    return;
  }
  return loadFullCatalog();
}

export async function maybeReleaseFullLeadsCatalog(targetTab = S.dashboardTab) {
  if (needsFullLeadsCatalog(targetTab)) return;
  if (!state.leads_full_loaded) return;
  state.leads = [];
  state.leads_full_loaded = false;
  state.archived_dials = [];
  state.dial_records = [];
  if (!Array.isArray(state.leads_summary) || state.leads_summary.length === 0) {
    await loadSummaryCatalog();
  }
}

export async function refreshLeadsIfStale(expectedVersion) {
  if (!leadsCatalogIsStale(expectedVersion)) {
    if (needsFullLeadsCatalog() && Array.isArray(state.leads)) return;
    if (!needsFullLeadsCatalog() && Array.isArray(state.leads_summary)) return;
  }
  await refreshLeadsCatalogForTab();
}

/** After a mutation: merge slim state, patch one lead, reload catalog when CRM revision moved. */
export async function applyMutationPayload(payload) {
  const before = state.leads_version;
  if (payload?.state) mergeLiveState(payload.state);
  if (payload?.state?.pipeline_steps?.length) {
    state.pipeline_steps = payload.state.pipeline_steps;
    state.pipeline_revision = payload.state.pipeline_revision ?? state.pipeline_revision;
    ensurePipelineRuntimeFromCatalog(payload.state);
  }
  if (payload?.lead) {
    mergeLeadPatch(state.leads, payload.lead);
    const slim = slimLeadRow(payload.lead);
    if (slim) mergeLeadPatch(state.leads_summary, slim);
  }
  const after = payload?.state?.leads_version ?? state.leads_version;
  if (leadsCatalogIsStale(after) || after !== before) {
    await refreshLeadsCatalogForTab();
  }
}

export async function loadAppState() {
  const live = await request("/api/live");
  mergeLiveState(live);
  await refreshLeadsIfStale(live.leads_version);
}