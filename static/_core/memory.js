import { S, seenSensoryActivity, state } from "./state.js";
import { wipeClientCatalogMemory } from "./sync-state.js";

function releaseHeavyDom() {
  void import("../features/_prospects/table.js").then((module) => module.releaseProspectsTableDom());
  void import("../features/_pipeline/board.js").then((module) => module.releasePipelineBoardDom());
  void import("../features/_workflow/campaign-crm-sidebar.js").then((module) => module.releaseWorkflowCrmSidebarDom());
}

/** Best-effort release before the tab is torn down; the browser still owns real GC. */
export function wipeClientMemory() {
  wipeClientCatalogMemory();
  seenSensoryActivity.clear();
  state.performance = null;
  state.metrics = { today: {}, all_time: {}, daily: [] };
  S.aiSandboxByAgent = {};
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