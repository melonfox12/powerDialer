import { postJson, request } from "../../_core/api.js";
import { arcadeSensory } from "../features/arcade/controller/index.js";
import { refreshAudioDevices } from "../features/voice/device/index.js";
import { stopMicrophoneTest } from "../features/voice/testing/index.js";
import { S, state } from "../../_core/state.js";
import { SECRET_INPUTS, byId, setText } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { render } from "../views/render.js";

const SECRET_FIELDS = SECRET_INPUTS;

export function applySavedSettings(settings) {
  state.settings = settings;
  byId("accountSidInput").value = settings.account_sid || "";
  byId("authTokenInput").value = settings.auth_token || "";
  byId("apiKeyInput").value = settings.api_key || "";
  byId("apiSecretInput").value = settings.api_secret || "";
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
    byId("settingsDialog").showModal();
  } catch (error) {
    showToast(error.message, true);
  }
}

export function bindSettings() {
  byId("settingsButton").addEventListener("click", openSettings);
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
      const settings = await postJson("/api/settings", {
        account_sid: byId("accountSidInput").value,
        auth_token: byId("authTokenInput").value,
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
      });
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
