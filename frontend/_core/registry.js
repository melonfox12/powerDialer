import { S, state } from "./state.js";

/** @typedef {"always"|"prospects"|"performance"|"pipeline"|"workflow"} RenderScope */

/** @type {{ fn: () => void, scope: RenderScope | RenderScope[] }[]} */
const renderers = [];
let tableRenderer = () => {};

export function registerRenderer(fn, position = "end", scope = "always") {
  const entry = { fn, scope };
  if (position === "start") renderers.unshift(entry);
  else renderers.push(entry);
}

/** Whether a scoped renderer should run on the current tab / session. */
export function rendererScopeEnabled(scope) {
  const tab = S.dashboardTab;
  const scopes = Array.isArray(scope) ? scope : [scope];
  for (const name of scopes) {
    switch (name) {
      case "always":
        return true;
      case "prospects":
        if (tab === "prospects") return true;
        break;
      case "pipeline":
        if (tab === "pipeline") return true;
        break;
      case "workflow":
        if (tab === "workflow") return true;
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