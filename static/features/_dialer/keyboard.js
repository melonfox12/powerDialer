import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";

export function bindKeyboard() {
  document.addEventListener("keydown", (event) => {
    const keyTarget = event.target instanceof Element ? event.target : null;
    if (keyTarget?.closest("input, textarea, select, [contenteditable=true]")) return;
    if ([...document.querySelectorAll("dialog")].some((dialog) => dialog.open)) return;
    if (!byId("loginGate").hidden) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    const onActivator = Boolean(keyTarget?.closest("button, a, summary"));
    if ((event.key === " " || event.key === "Enter") && onActivator) return;
    if (event.key === " " && !event.repeat && !state.running) {
      event.preventDefault();
      byId("startButton").click();
    }
  });
}
