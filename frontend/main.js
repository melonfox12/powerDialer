import { bindDebugListeners } from "./_core/api.js";
import { bindAuth, initAuth, showLoginGate } from "./features/auth.js";
import { bindNavigation, renderTable } from "./core.js";
import "./features/pipeline.js";
import { bindWorkflow } from "./features/workflow.js";
import { bindAddProspect, bindCsv, bindDialogs, bindProspectMenu, bindProspects } from "./features/prospects.js";
import { bindSettings } from "./features/settings.js";
import { byId, startStatusClock } from "./_core/format.js";
import { bindClientMemoryLifecycle } from "./_core/memory.js";
import { wipeClientCatalogMemory } from "./_core/sync-state.js";
import { startPolling } from "./_core/poller.js";

wipeClientCatalogMemory();
bindClientMemoryLifecycle();
bindDebugListeners();
startStatusClock();
bindWorkflow();
bindDialogs();
bindProspects();
bindAddProspect();
bindProspectMenu();
bindSettings();
bindCsv();
byId("searchInput").addEventListener("input", renderTable);
byId("statusFilter").addEventListener("change", renderTable);
byId("stateFilter").addEventListener("change", renderTable);
for (const id of ["minTotalReviews", "maxTotalReviews", "minRecentReviews"]) {
  byId(id).addEventListener("input", renderTable);
}
bindAuth();
initAuth()
  .catch((error) => showLoginGate(error.message || "Could not start sign-in."))
  .finally(() => {
    bindNavigation();
    startPolling();
  });