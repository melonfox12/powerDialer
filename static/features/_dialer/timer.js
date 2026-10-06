import { S, state } from "../../_core/state.js";

export function stopCallTimer() {
  clearInterval(S.callTimerId);
  S.callTimerId = null;
}

export function startCallTimer(startedMs) {
  stopCallTimer();
  const node = document.getElementById("callTimer");
  if (!node) return;
  const tick = () => {
    if (!node.isConnected || (state.stage || "idle") !== "connected") {
      stopCallTimer();
      return;
    }
    const seconds = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
    node.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick();
  S.callTimerId = setInterval(tick, 1000);
}
