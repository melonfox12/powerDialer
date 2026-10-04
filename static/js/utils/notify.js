import { byId } from "./format.js";

let toastTimer;

export function showToast(message, isError = false) {
  if (isError) showToast.report?.(message);
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}
