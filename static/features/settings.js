import { arcadeSensory } from "./arcade.js";
import { postJson, refreshAudioDevices, render, request, SECRET_INPUTS, S, byId, setText, showToast, state, stopMicrophoneTest } from "../core.js";

const SECRET_FIELDS = SECRET_INPUTS;
const SAVED_SECRET_PLACEHOLDER = "Saved — leave blank to keep";

function showSecretField(id, saved) {
  const input = byId(id);
  if (input.value) return;
  input.placeholder = saved ? SAVED_SECRET_PLACEHOLDER : "";
}

function resetAuthTokenField(saved) {
  const input = byId("authTokenInput");
  if (input.dataset.edited === "1") return;
  input.value = "";
  input.readOnly = true;
  input.placeholder = saved ? SAVED_SECRET_PLACEHOLDER : "";
}

function authTokenToSave() {
  const input = byId("authTokenInput");
  if (input.dataset.edited === "1") return input.value.trim();
  return "";
}

export function applySavedSettings(settings) {
  state.settings = settings;
  byId("accountSidInput").value = settings.account_sid || "";
  resetAuthTokenField(settings.has_auth_token);
  const apiKey = byId("apiKeyInput");
  apiKey.value = settings.api_key || "";
  apiKey.readOnly = true;
  byId("apiSecretInput").value = settings.api_secret || "";
  showSecretField("apiSecretInput", settings.has_api_secret);
  byId("twimlAppSidInput").value = settings.twiml_app_sid || "";
  byId("publicUrlInput").value = settings.public_base_url || "";
  byId("sessionGoalInput").value = settings.session_goal;
  byId("conversationThresholdInput").value = settings.conversation_threshold;
  byId("autoAdvanceDelayInput").value = settings.auto_advance_delay;
  byId("callingStartHourInput").value = settings.calling_start_hour;
  byId("callingEndHourInput").value = settings.calling_end_hour;
  byId("breakNudgeInput").value = settings.break_nudge_minutes;
  byId("openingScriptInput").value = settings.opening_script || "";
  byId("soundsEnabledInput").checked = settings.sounds_enabled;
  byId("soundVolumeInput").value = settings.sound_volume;
  setText("soundVolumeValue", `${settings.sound_volume}%`);
}

function maskSecrets() {
  for (const [id, noun] of SECRET_FIELDS) {
    const input = byId(id);
    const button = document.querySelector(`[data-reveal="${id}"]`);
    input.type = "password";
    if (!button) continue;
    button.textContent = "Show";
    button.setAttribute("aria-pressed", "false");
    button.setAttribute("aria-label", `Show ${noun}`);
  }
}

export async function openSettings() {
  try {
    const settings = await request("/api/settings");
    applySavedSettings(settings);
    maskSecrets();
    arcadeSensory.syncControls();
    await refreshAudioDevices();
    const dialog = byId("settingsDialog");
    dialog.showModal();
    applySavedSettings(settings);
    requestAnimationFrame(() => applySavedSettings(settings));
  } catch (error) {
    showToast(error.message, true);
  }
}

function settingsPayload() {
  return {
    account_sid: byId("accountSidInput").value,
    auth_token: authTokenToSave(),
    api_key: byId("apiKeyInput").value,
    api_secret: byId("apiSecretInput").value,
    twiml_app_sid: byId("twimlAppSidInput").value,
    public_base_url: byId("publicUrlInput").value,
    session_goal: byId("sessionGoalInput").value,
    conversation_threshold: byId("conversationThresholdInput").value,
    auto_advance_delay: byId("autoAdvanceDelayInput").value,
    calling_start_hour: byId("callingStartHourInput").value,
    calling_end_hour: byId("callingEndHourInput").value,
    break_nudge_minutes: byId("breakNudgeInput").value,
    opening_script: byId("openingScriptInput").value,
    sounds_enabled: byId("soundsEnabledInput").checked,
    sound_volume: byId("soundVolumeInput").value,
  };
}

export function bindSettings() {
  byId("settingsButton").addEventListener("click", openSettings);
  byId("apiKeyInput").addEventListener("focus", (event) => {
    event.target.readOnly = false;
  });
  const authToken = byId("authTokenInput");
  const unlockAuthToken = (event) => {
    event.currentTarget.readOnly = false;
  };
  authToken.addEventListener("pointerdown", unlockAuthToken);
  authToken.addEventListener("focus", unlockAuthToken);
  authToken.addEventListener("input", (event) => {
    const typed = event.isTrusted && event.inputType && event.inputType !== "insertReplacementText";
    if (typed) event.target.dataset.edited = "1";
  });
  for (const [id, noun] of SECRET_FIELDS) {
    const button = document.querySelector(`[data-reveal="${id}"]`);
    button?.addEventListener("click", () => {
      const input = byId(id);
      const reveal = input.type === "password";
      input.type = reveal ? "text" : "password";
      button.textContent = reveal ? "Hide" : "Show";
      button.setAttribute("aria-pressed", reveal ? "true" : "false");
      button.setAttribute("aria-label", `${reveal ? "Hide" : "Show"} ${noun}`);
    });
  }
  byId("settingsDialog").addEventListener("close", () => {
    if (S.micTestRecorder?.state === "recording") {
      stopMicrophoneTest().catch((error) => showToast(error.message, true));
    }
  });
  byId("closeSettings").addEventListener("click", () => byId("settingsDialog").close());
  byId("cancelSettings").addEventListener("click", () => byId("settingsDialog").close());
  byId("settingsForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = byId("settingsForm").querySelector("[type=submit]");
    submit.disabled = true;
    try {
      const settings = await postJson("/api/settings", settingsPayload());
      delete byId("authTokenInput").dataset.edited;
      applySavedSettings(settings);
      maskSecrets();
      byId("settingsDialog").close();
      render();
      showToast(settings.account_email ? `Settings saved for ${settings.account_email}` : "Dialer settings saved");
    } catch (error) {
      showToast(error.message, true);
    } finally {
      submit.disabled = false;
    }
  });
  byId("soundVolumeInput").addEventListener("input", (event) => {
    setText("soundVolumeValue", `${event.target.value}%`);
  });
}
