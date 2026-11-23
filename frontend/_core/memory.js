import { S, seenSensoryActivity, state } from "./state.js";
<<<<<<< HEAD:frontend/_core/memory.js

function releaseHeavyDom() {
  void import("../features/_prospects/table.js").then((module) => module.releaseProspectsTableDom?.());
=======
import { wipeClientCatalogMemory } from "./sync-state.js";

function releaseHeavyDom() {
  void import("../features/_prospects/table.js").then((module) => module.releaseProspectsTableDom());
  void import("../features/_pipeline/board.js").then((module) => module.releasePipelineBoardDom());
  void import("../features/_workflow/campaign-crm-sidebar.js").then((module) => module.releaseWorkflowCrmSidebarDom());
>>>>>>> 1f6194cd2ae87ec7fff49dab3cbd173c490ead53:static/_core/memory.js
}

/** Best-effort release before the tab is torn down; the browser still owns real GC. */
export function wipeClientMemory() {
<<<<<<< HEAD:frontend/_core/memory.js
  seenSensoryActivity.clear();
  state.performance = null;
  state.metrics = { today: {}, all_time: {}, daily: [] };
=======
  wipeClientCatalogMemory();
  seenSensoryActivity.clear();
  state.performance = null;
  state.metrics = { today: {}, all_time: {}, daily: [] };
  S.aiSandboxByAgent = {};
>>>>>>> 1f6194cd2ae87ec7fff49dab3cbd173c490ead53:static/_core/memory.js
  S.performancePainted = null;
  releaseHeavyDom();
}

export function bindClientMemoryLifecycle() {
  window.addEventListener(
    "pagehide",
    () => {
      wipeClientMemory();
    },
    { capture: true },
  );

  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    wipeClientMemory();
    void import("../features/dialer.js").then((module) => module.refreshState().catch(() => {}));
  });
}