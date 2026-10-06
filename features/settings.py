"""Preference validation, settings view, and env or account persistence."""

from shared.config import read_env, write_env
from shared.vocabulary import REMOTE_SETTING_KEYS, SETTING_DEFAULTS, SETTINGS_ROW_ID


def preferences(values):
    result = dict(SETTING_DEFAULTS)
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


def values(env_path, account_values):
    return {**read_env(env_path), **account_values}


def settings_state(env_path, account_values, storage_name="local JSON files", account_email=""):
    current = values(env_path, account_values)
    parsed = preferences(current)
    return {
        "account_sid": current.get("TWILIO_ACCOUNT_SID", ""),
        "auth_token": current.get("TWILIO_AUTH_TOKEN", ""),
        "api_key": current.get("TWILIO_API_KEY", ""),
        "api_secret": current.get("TWILIO_API_SECRET", ""),
        "twiml_app_sid": current.get("TWILIO_TWIML_APP_SID", ""),
        "public_base_url": current.get("PUBLIC_BASE_URL", ""),
        "has_auth_token": bool(current.get("TWILIO_AUTH_TOKEN")),
        "has_api_secret": bool(current.get("TWILIO_API_SECRET")),
        "storage": storage_name or "local JSON files",
        "account_email": account_email or "",
        "session_goal": int(parsed["SESSION_GOAL"]),
        "conversation_threshold": int(parsed["CONVERSATION_THRESHOLD_SECONDS"]),
        "auto_advance_delay": int(parsed["AUTO_ADVANCE_DELAY_SECONDS"]),
        "sounds_enabled": parsed["SOUNDS_ENABLED"].lower() == "true",
        "sound_volume": int(parsed["SOUND_VOLUME"]),
        "break_nudge_minutes": int(parsed["BREAK_NUDGE_MINUTES"]),
        "calling_start_hour": int(parsed["CALLING_START_HOUR"]),
        "calling_end_hour": int(parsed["CALLING_END_HOUR"]),
        "opening_script": parsed["OPENING_SCRIPT"],
    }


def save_settings(env_path, account_values, account_user_id, data, save_remote=None):
    parsed = preferences({
        **values(env_path, account_values),
        "SESSION_GOAL": data.get("session_goal", SETTING_DEFAULTS["SESSION_GOAL"]),
        "CONVERSATION_THRESHOLD_SECONDS": data.get("conversation_threshold", SETTING_DEFAULTS["CONVERSATION_THRESHOLD_SECONDS"]),
        "AUTO_ADVANCE_DELAY_SECONDS": data.get("auto_advance_delay", SETTING_DEFAULTS["AUTO_ADVANCE_DELAY_SECONDS"]),
        "SOUNDS_ENABLED": str(data.get("sounds_enabled", True)).lower(),
        "SOUND_VOLUME": data.get("sound_volume", SETTING_DEFAULTS["SOUND_VOLUME"]),
        "BREAK_NUDGE_MINUTES": data.get("break_nudge_minutes", SETTING_DEFAULTS["BREAK_NUDGE_MINUTES"]),
        "CALLING_START_HOUR": data.get("calling_start_hour", SETTING_DEFAULTS["CALLING_START_HOUR"]),
        "CALLING_END_HOUR": data.get("calling_end_hour", SETTING_DEFAULTS["CALLING_END_HOUR"]),
        "OPENING_SCRIPT": data.get("opening_script", ""),
    })
    current = values(env_path, account_values)
    updates = {
        "TWILIO_ACCOUNT_SID": str(data.get("account_sid", "")),
        "TWILIO_AUTH_TOKEN": str(data.get("auth_token", "")),
        "TWILIO_API_KEY": str(data.get("api_key", "")),
        "TWILIO_API_SECRET": str(data.get("api_secret", "")),
        "TWILIO_TWIML_APP_SID": str(data.get("twiml_app_sid", "")),
        "PUBLIC_BASE_URL": str(data.get("public_base_url", "")).rstrip("/"),
        **parsed,
    }
    if not updates["TWILIO_AUTH_TOKEN"]:
        updates["TWILIO_AUTH_TOKEN"] = current.get("TWILIO_AUTH_TOKEN", "")
    if not updates["TWILIO_API_SECRET"]:
        updates["TWILIO_API_SECRET"] = current.get("TWILIO_API_SECRET", "")
    if account_user_id:
        account_values.update(updates)
        if save_remote:
            save_remote(values(env_path, account_values))
    else:
        write_env(env_path, updates)
    return parsed


def load_app_settings(client, user_id=None):
    row_id = str(user_id or SETTINGS_ROW_ID)
    try:
        rows = client.request(
            "GET",
            "dialer_settings",
            {"id": f"eq.{row_id}", "select": "data"},
        )
    except OSError as exc:
        if "HTTP 404" in str(exc) or "PGRST205" in str(exc) or "does not exist" in str(exc).lower():
            return {}
        raise
    if not rows:
        return {}
    if not isinstance(rows, list) or not isinstance(rows[0], dict) or not isinstance(rows[0].get("data"), dict):
        raise OSError("Supabase returned invalid dialer settings.")
    stored = rows[0]["data"]
    return {
        key: str(stored[key])
        for key in REMOTE_SETTING_KEYS
        if stored.get(key) not in (None, "")
    }


def save_app_settings(client, stored_values, user_id=None):
    payload = {
        "id": str(user_id or SETTINGS_ROW_ID),
        "data": {key: str(stored_values.get(key, "") or "") for key in REMOTE_SETTING_KEYS},
    }
    client.request(
        "POST",
        "dialer_settings",
        {"on_conflict": "id"},
        [payload],
        "resolution=merge-duplicates,return=minimal",
    )


def get_settings(request):
    request.ctx.reload_settings()
    request.send_json(200, request.ctx.settings_view())


def post_settings(request, data):
    request.ctx.save_posted_settings(data)
    request.send_json(200, request.ctx.settings_view())


ROUTES = [
    ("GET", "/api/settings", get_settings, "none"),
    ("POST", "/api/settings", post_settings, "POST"),
]
