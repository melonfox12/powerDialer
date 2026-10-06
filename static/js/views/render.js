import { runRenderers } from "../../core.js";
import { S, state } from "../../_core/state.js";
import { byId, setText } from "../../_core/format.js";
import { renderMetrics } from "../../features/performance.js";
import { crmTableSignature, renderTable } from "./prospects-table/index.js";

export function render() {
  byId("headingImportButton").hidden = state.leads.length > 0;
  setText("prospectTabCount", String(state.counts?.total ?? state.leads.length));
  if (crmTableSignature() !== S.lastCrmTableSignature) renderTable();
  runRenderers();
  renderMetrics();
}
