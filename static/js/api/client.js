import { S } from "../store/state.js";
import { showToast } from "../utils/notify.js";

let onUnauthorized = () => {};

export function setUnauthorizedHandler(handler) {
  onUnauthorized = handler;
}

showToast.report = (message) => debugEvent("error", "toast", message);

export function debugEvent(level, message, detail = "") {
  if (level === "error") {
    const key = `${message}|${detail}`;
    const now = Date.now();
    if (key === debugEvent.lastKey && now - debugEvent.lastAt < 4000) return;
    debugEvent.lastKey = key;
    debugEvent.lastAt = now;
  }
  const body = JSON.stringify({
    level,
    message: String(message || "").slice(0, 300),
    detail: String(detail || "").slice(0, 300),
  });
  fetch("/api/debug", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    keepalive: true,
  }).catch(() => {});
}

export async function request(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (S.accessToken) headers.Authorization = `Bearer ${S.accessToken}`;
  const method = options.method || "GET";
  let response;
  try {
    response = await fetch(path, { ...options, headers });
  } catch (error) {
    debugEvent("error", `${method} ${path}`, error?.message || "network error");
    throw error;
  }
  const type = response.headers.get("content-type") || "";
  const result = type.includes("application/json") ? await response.json() : await response.text();
  if (response.status === 401 && S.googleAuthEnabled) {
    onUnauthorized(result?.error || "Sign in with Google to continue.");
    throw new Error(result?.error || "Sign in with Google to continue.");
  }
  if (!response.ok) throw new Error(result?.error || `Request failed (${response.status})`);
  return result;
}

export function postJson(path, payload = {}) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function bindDebugListeners() {
  window.addEventListener("error", (event) => {
    console.error("Unhandled error:", event.error || event.message);
    debugEvent("error", "unhandled", event.message);
    showToast(`Unexpected error: ${event.message}`, true);
  });
  window.addEventListener("unhandledrejection", (event) => {
    console.error("Unhandled promise rejection:", event.reason);
    debugEvent("error", "unhandled rejection", event.reason?.message || String(event.reason));
    showToast(`Unexpected error: ${event.reason?.message || event.reason}`, true);
  });
  document.addEventListener("click", (event) => {
    const target = event.target.closest("button, a, summary, [role='button']");
    if (!target) return;
    const label = (target.getAttribute("aria-label") || target.innerText || "").trim().replace(/\s+/g, " ").slice(0, 80);
    debugEvent("ui", `click ${target.id || target.tagName.toLowerCase()}`, label);
  }, true);
  document.addEventListener("change", (event) => {
    const element = event.target;
    if (!(element instanceof HTMLElement) || !element.id) return;
    const sensitive = Boolean(element.closest("#settingsForm")) || /secret|token|password|key/i.test(element.id);
    debugEvent("ui", `change ${element.id}`, sensitive ? "(hidden)" : String(element.value || "").slice(0, 80));
  }, true);
}
