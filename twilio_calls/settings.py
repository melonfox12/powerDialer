"""Twilio call coordination for the local CRM dialer."""

import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from debug_log import debug_event
from dialer_session import (
    add_connect, dialer_stage, new_session, recent_streak, record_conversation,
    record_disposition,
    local_time, session_summary, status_for_disposition, within_calling_window,
)
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}"
DIALER_DEFAULTS = {
    "SESSION_GOAL": "20",
    "CONVERSATION_THRESHOLD_SECONDS": "30",
    "AUTO_ADVANCE_DELAY_SECONDS": "3",
    "SOUNDS_ENABLED": "true",
    "SOUND_VOLUME": "35",
    "BREAK_NUDGE_MINUTES": "90",
    "CALLING_START_HOUR": "8",
    "CALLING_END_HOUR": "21",
    "OPENING_SCRIPT": "",
}


def _preferences(values):
    result = dict(DIALER_DEFAULTS)
    for key in result:
        provided = str(values[key] if values.get(key) is not None else "").strip()
        if key == "OPENING_SCRIPT":
            result[key] = str(values.get(key) or "")
        elif provided:
            result[key] = provided
    for key, minimum, maximum in (
        ("SESSION_GOAL", 1, 1000),
        ("CONVERSATION_THRESHOLD_SECONDS", 1, 3600),
        ("AUTO_ADVANCE_DELAY_SECONDS", 0, 60),
        ("SOUND_VOLUME", 0, 100),
        ("BREAK_NUDGE_MINUTES", 1, 720),
        ("CALLING_START_HOUR", 0, 23),
        ("CALLING_END_HOUR", 1, 24),
    ):
        try:
            value = int(result[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{key.replace('_', ' ').title()} must be a whole number.") from exc
        if not minimum <= value <= maximum:
            raise ValueError(f"{key.replace('_', ' ').title()} must be between {minimum} and {maximum}.")
        result[key] = str(value)
    if int(result["CALLING_START_HOUR"]) >= int(result["CALLING_END_HOUR"]):
        raise ValueError("Calling-hours end must be later than its start.")
    if result["SOUNDS_ENABLED"].lower() not in ("true", "false"):
        raise ValueError("Sounds enabled must be true or false.")
    if len(result["OPENING_SCRIPT"]) > 2000:
        raise ValueError("Opening script must be 2,000 characters or fewer.")
    return result

def read_env(path):
    values = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "OPENING_SCRIPT":
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                    else:
                        value = value.strip('"').strip("'")
                    values[key] = value
    for key in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
        "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY",
        "SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY",
        *DIALER_DEFAULTS.keys(),
    ):
        values.setdefault(key, os.environ.get(key, ""))
    return values


def write_env(path, updates):
    values = read_env(path)
    for key, value in updates.items():
        stripped = str(value).strip()
        if key == "OPENING_SCRIPT":
            values[key] = json.dumps(stripped, ensure_ascii=False)
        elif stripped:
            values[key] = stripped
        elif key in DIALER_DEFAULTS:
            values[key] = DIALER_DEFAULTS[key]
        else:
            values[key] = ""
    lines = [f"{key}={value}" for key, value in values.items() if value]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return values

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
