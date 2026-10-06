import { byId, setText } from "./format.js";
import { runRenderers } from "./registry.js";
import { state } from "./state.js";

export function render() {
  byId("headingImportButton").hidden = state.leads.length > 0;
  setText("prospectTabCount", String(state.counts?.total ?? state.leads.length));
  runRenderers();
}
