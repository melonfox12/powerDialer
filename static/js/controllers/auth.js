import { request, setUnauthorizedHandler } from "../../_core/api.js";
import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { drawProspectWaveform } from "../views/dialer/card.js";
import { refreshState } from "./poller.js";
import { applySavedSettings } from "./settings.js";

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
  drawProspectWaveform(0);
  refreshState();
  request("/api/settings").then((settings) => {
    applySavedSettings(settings);
    if (!settings.account_sid || !settings.has_auth_token || !settings.api_key || !settings.has_api_secret || !settings.twiml_app_sid || !settings.public_base_url) {
      showToast("Complete your Twilio Voice credentials and callback URL in Settings to start dialing.");
    }
  }).catch(() => {});
}

export async function initAuth() {
  const config = await fetch("/api/auth/config").then((response) => response.json());
  S.googleAuthEnabled = Boolean(config.google && window.supabase?.createClient);
  if (!S.googleAuthEnabled) {
    await bootApp();
    return;
  }
  S.supabaseClient = window.supabase.createClient(config.url, config.anonKey);
  S.supabaseClient.auth.onAuthStateChange((_event, session) => {
    S.accessToken = session?.access_token || null;
    syncAccountChrome(session);
  });
  const { data: { session } } = await S.supabaseClient.auth.getSession();
  S.accessToken = session?.access_token || null;
  syncAccountChrome(session);
  if (session) {
    await bootApp();
    return;
  }
  showLoginGate();
}

export function bindAuth() {
  byId("googleSignInButton").addEventListener("click", async () => {
    if (!S.supabaseClient) return;
    const { error } = await S.supabaseClient.auth.signInWithOAuth({
      provider: "google",
      options: { redirectTo: window.location.origin + "/" },
    });
    if (error) showLoginGate(error.message);
  });
  byId("signOutButton").addEventListener("click", async () => {
    S.accessToken = null;
    await S.supabaseClient?.auth.signOut();
    showLoginGate();
  });
}
