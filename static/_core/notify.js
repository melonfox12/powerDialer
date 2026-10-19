import { byId } from "./format.js";

let toastTimer;

export function errorText(error, fallback = "Something went wrong.") {
  if (typeof error === "string" && error.trim()) return error.trim();
  if (error && typeof error === "object") {
    if (typeof error.message === "string" && error.message.trim()) return error.message.trim();
    if (error.code) return `${fallback} (${error.code})`;
  }
  return fallback;
}

export function showToast(message, isError = false) {
  if (isError) showToast.report?.(message);
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}
