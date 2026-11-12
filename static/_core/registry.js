import { S, state } from "./state.js";

/** @typedef {"always"|"dialer"|"aiDialerAgent"|"dialFilters"|"prospects"|"performance"|"pipeline"|"pool"|"dials"} RenderScope */

/** @type {{ fn: () => void, scope: RenderScope | RenderScope[] }[]} */
const renderers = [];
let callerPoolRenderer = () => {};
let tableRenderer = () => {};

export function registerRenderer(fn, position = "end", scope = "always") {
  const entry = { fn, scope };
  if (position === "start") renderers.unshift(entry);
  else renderers.push(entry);
}

function dialerSessionActive() {
  return Boolean(state.running || state.pending_outcome || state.active_lead);
}

/** Whether a scoped renderer should run on the current tab / session. */
export function rendererScopeEnabled(scope) {
  const tab = S.dashboardTab;
  const scopes = Array.isArray(scope) ? scope : [scope];
  for (const name of scopes) {
    switch (name) {
      case "always":
        return true;
      case "dialer":
        if (tab === "dialer") return true;
        break;
      case "aiDialerAgent":
        if (tab === "aiDialerAgent") return true;
        break;
      case "dialFilters":
        if (tab === "dialer" || tab === "pool") return true;
        break;
      case "dialerLive":
        if (dialerSessionActive() && (tab === "dialer" || tab === "aiDialerAgent")) return true;
        break;
      case "prospects":
        if (tab === "prospects") return true;
        break;
      case "performance":
        if (tab === "performance") return true;
        break;
      case "pipeline":
        if (tab === "pipeline") return true;
        break;
      case "pool":
        if (tab === "pool") return true;
        break;
      case "dials":
        if (tab === "dials") return true;
        break;
      default:
        break;
    }
  }
  return false;
}

export function runRenderers() {
  for (const { fn, scope } of renderers) {
    if (rendererScopeEnabled(scope)) fn();
  }
}

export function registerTable(fn) {
  tableRenderer = fn;
}

export function renderTable() {
  tableRenderer();
}

export function registerCallerPool(fn) {
  callerPoolRenderer = fn;
}

export function renderCallerPool() {
  callerPoolRenderer();
}
