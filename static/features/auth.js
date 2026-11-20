import { byId, render, request, S, setUnauthorizedHandler, showToast } from "../core.js";
import { drawProspectWaveform, refreshState } from "./dialer.js";
import { applySavedSettings } from "./settings.js";

let supabaseClient = null;
let appBooted = false;

/** @type {() => void} */
let resolveAuthReady = () => {};
export const authReady = new Promise((resolve) => {
  resolveAuthReady = resolve;
});

setUnauthorizedHandler(showLoginGate);

export function showLoginGate(message) {
  const gate = byId("loginGate");
  const error = byId("loginError");
  gate.hidden = false;
  document.querySelector(".app-shell")?.setAttribute("hidden", "hidden");
  if (message) {
    error.hidden = false;
    error.textContent = message;
  } else {
    error.hidden = true;
  }
}

export function hideLoginGate() {
  byId("loginGate").hidden = true;
  document.querySelector(".app-shell")?.removeAttribute("hidden");
}

export function syncAccountChrome(session) {
  const email = session?.user?.email || "";
  const emailEl = byId("accountEmail");
  const signOut = byId("signOutButton");
  emailEl.hidden = !email;
  signOut.hidden = !S.googleAuthEnabled;
  emailEl.textContent = email;
}

export async function bootApp() {
  hideLoginGate();
  if (appBooted) return;
  appBooted = true;
  drawProspectWaveform(0);
  S.performanceFetchedAt = 0;
  refreshState();
  request("/api/settings").then((settings) => {
    applySavedSettings(settings);
    if (!settings.account_sid || !settings.has_auth_token || !settings.api_key || !settings.has_api_secret || !settings.twiml_app_sid || !settings.public_base_url) {
      showToast("Complete your Twilio Voice credentials and callback URL in Settings to start dialing.");
    }
  }).catch(() => {});
}

export async function initAuth() {
  S.authBootstrapping = true;
  try {
    const config = await fetch("/api/auth/config").then((response) => response.json());
    S.googleAuthEnabled = Boolean(config.google && window.supabase?.createClient);
    if (!S.googleAuthEnabled) {
      await bootApp();
      return;
    }
    supabaseClient = window.supabase.createClient(config.url, config.anonKey);
    supabaseClient.auth.onAuthStateChange((_event, session) => {
      S.accessToken = session?.access_token || null;
      syncAccountChrome(session);
      if (session?.access_token) {
        hideLoginGate();
        if (!appBooted) void bootApp();
      } else if (appBooted && !S.authBootstrapping) {
        showLoginGate();
      }
      if (session?.access_token && S.dashboardTab === "performance") {
        S.performanceFetchedAt = 0;
        render();
      }
    });
    let session = (await supabaseClient.auth.getSession()).data.session;
    if (!session?.access_token) {
      await new Promise((resolve) => requestAnimationFrame(resolve));
      session = (await supabaseClient.auth.getSession()).data.session;
    }
    S.accessToken = session?.access_token || null;
    syncAccountChrome(session);
    if (session?.access_token) {
      await bootApp();
      return;
    }
    showLoginGate();
  } finally {
    S.authBootstrapping = false;
    resolveAuthReady();
  }
}

export function bindAuth() {
  byId("googleSignInButton").addEventListener("click", async () => {
    if (!supabaseClient) return;
    const { error } = await supabaseClient.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin + "/" },
    });
    if (error) showLoginGate(error.message);
  });
  byId("signOutButton").addEventListener("click", async () => {
    S.accessToken = null;
    appBooted = false;
    await supabaseClient?.auth.signOut();
    showLoginGate();
  });
}
