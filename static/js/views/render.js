import { S, state } from "../store/state.js";
import { byId, setText } from "../utils/format.js";
import { renderCallerPool } from "./caller-pool.js";
import { renderDialer } from "./dialer.js";
import { renderMetrics } from "./metrics.js";
import { crmTableSignature, renderTable } from "./prospects-table/index.js";

export function render() {
  byId("headingImportButton").hidden = state.leads.length > 0;
  setText("prospectTabCount", String(state.counts?.total ?? state.leads.length));
  if (crmTableSignature() !== S.lastCrmTableSignature) renderTable();
  renderCallerPool();
  renderDialer();
  renderMetrics();
}
