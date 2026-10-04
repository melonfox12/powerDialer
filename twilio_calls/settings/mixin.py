from twilio_calls.settings.defaults import DIALER_DEFAULTS
from twilio_calls.settings.defaults import _preferences
from twilio_calls.settings.defaults import read_env
from twilio_calls.settings.defaults import write_env

class SettingsMixin:
    def _values(self):
        return {**read_env(self.env_path), **self.account_values}

    def settings_state(self):
        values = self._values()
        preferences = _preferences(values)
        return {
            "account_sid": values.get("TWILIO_ACCOUNT_SID", ""),
            "api_key": values.get("TWILIO_API_KEY", ""),
            "twiml_app_sid": values.get("TWILIO_TWIML_APP_SID", ""),
            "public_base_url": values.get("PUBLIC_BASE_URL", ""),
            "has_auth_token": bool(values.get("TWILIO_AUTH_TOKEN")),
            "has_api_secret": bool(values.get("TWILIO_API_SECRET")),
            "storage": getattr(self, "storage_name", "local JSON files"),
            "account_email": getattr(self, "account_email", ""),
            "session_goal": int(preferences["SESSION_GOAL"]),
            "conversation_threshold": int(preferences["CONVERSATION_THRESHOLD_SECONDS"]),
            "auto_advance_delay": int(preferences["AUTO_ADVANCE_DELAY_SECONDS"]),
            "sounds_enabled": preferences["SOUNDS_ENABLED"].lower() == "true",
            "sound_volume": int(preferences["SOUND_VOLUME"]),
            "break_nudge_minutes": int(preferences["BREAK_NUDGE_MINUTES"]),
            "calling_start_hour": int(preferences["CALLING_START_HOUR"]),
            "calling_end_hour": int(preferences["CALLING_END_HOUR"]),
            "opening_script": preferences["OPENING_SCRIPT"],
        }

    def save_settings(self, data):
        preferences = _preferences({
            **self._values(),
            "SESSION_GOAL": data.get("session_goal", DIALER_DEFAULTS["SESSION_GOAL"]),
            "CONVERSATION_THRESHOLD_SECONDS": data.get("conversation_threshold", DIALER_DEFAULTS["CONVERSATION_THRESHOLD_SECONDS"]),
            "AUTO_ADVANCE_DELAY_SECONDS": data.get("auto_advance_delay", DIALER_DEFAULTS["AUTO_ADVANCE_DELAY_SECONDS"]),
            "SOUNDS_ENABLED": str(data.get("sounds_enabled", True)).lower(),
            "SOUND_VOLUME": data.get("sound_volume", DIALER_DEFAULTS["SOUND_VOLUME"]),
            "BREAK_NUDGE_MINUTES": data.get("break_nudge_minutes", DIALER_DEFAULTS["BREAK_NUDGE_MINUTES"]),
            "CALLING_START_HOUR": data.get("calling_start_hour", DIALER_DEFAULTS["CALLING_START_HOUR"]),
            "CALLING_END_HOUR": data.get("calling_end_hour", DIALER_DEFAULTS["CALLING_END_HOUR"]),
            "OPENING_SCRIPT": data.get("opening_script", ""),
        })
        current = self._values()
        updates = {
            "TWILIO_ACCOUNT_SID": str(data.get("account_sid", "")),
            "TWILIO_AUTH_TOKEN": str(data.get("auth_token", "")),
            "TWILIO_API_KEY": str(data.get("api_key", "")),
            "TWILIO_API_SECRET": str(data.get("api_secret", "")),
            "TWILIO_TWIML_APP_SID": str(data.get("twiml_app_sid", "")),
            "PUBLIC_BASE_URL": str(data.get("public_base_url", "")).rstrip("/"),
            **preferences,
        }
        if not updates["TWILIO_AUTH_TOKEN"]:
            updates["TWILIO_AUTH_TOKEN"] = current.get("TWILIO_AUTH_TOKEN", "")
        if not updates["TWILIO_API_SECRET"]:
            updates["TWILIO_API_SECRET"] = current.get("TWILIO_API_SECRET", "")
        if self.account_user_id:
            self.account_values.update(updates)
            saver = getattr(self, "settings_saver", None)
            if saver:
                saver(self)
        else:
            write_env(self.env_path, updates)
        with self.lock:
            self.settings.update(preferences)
        return self.settings_state()
