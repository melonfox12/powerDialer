import { S, seenSensoryActivity, state } from "./state.js";

function releaseHeavyDom() {
  void import("../features/_prospects/table.js").then((module) => module.releaseProspectsTableDom?.());
}

/** Best-effort release before the tab is torn down; the browser still owns real GC. */
export function wipeClientMemory() {
  seenSensoryActivity.clear();
  state.performance = null;
  state.metrics = { today: {}, all_time: {}, daily: [] };
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