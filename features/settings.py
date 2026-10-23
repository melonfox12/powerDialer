"""Preference validation, settings view, and env or account persistence."""

from datetime import date

from shared.config import read_env, write_env
from shared.vocabulary import (
    DAILY_GOAL_MAX_MINUTES,
    REMOTE_SETTING_KEYS,
    SETTING_DEFAULTS,
    SETTINGS_ROW_ID,
    TWILIO_ACCOUNT_KEYS,
)


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
        ("DAILY_GOAL_MINUTES", 1, DAILY_GOAL_MAX_MINUTES),
        ("DAILY_CONVERSATION_GOAL", 1, 1000),
        ("DAILY_GOAL_WEEKLY_STEP_MINUTES", 0, DAILY_GOAL_MAX_MINUTES),
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
    if result["DAILY_GOAL_ANCHOR"]:
        try:
            date.fromisoformat(result["DAILY_GOAL_ANCHOR"])
        except ValueError as exc:
            raise ValueError("Daily goal start date must be a valid date.") from exc
    if result["SOUNDS_ENABLED"].lower() not in ("true", "false"):
        raise ValueError("Sounds enabled must be true or false.")
    if len(result["OPENING_SCRIPT"]) > 2000:
        raise ValueError("Opening script must be 2,000 characters or fewer.")
    return result


def values(env_path, account_values, *, signed_in):
    server = read_env(env_path)
    if signed_in:
        server = {key: "" if key in TWILIO_ACCOUNT_KEYS else value for key, value in server.items()}
    return {**server, **account_values}


def settings_state(env_path, account_values, storage_name="local JSON files", account_email="", *, signed_in):
    current = values(env_path, account_values, signed_in=signed_in)
    parsed = preferences(current)
    return {
        "account_sid": current.get("TWILIO_ACCOUNT_SID", ""),
        "auth_token": "",
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
        "daily_goal_minutes": int(parsed["DAILY_GOAL_MINUTES"]),
        "daily_conversation_goal": int(parsed["DAILY_CONVERSATION_GOAL"]),
        "daily_goal_weekly_step": int(parsed["DAILY_GOAL_WEEKLY_STEP_MINUTES"]),
        "daily_goal_anchor": parsed["DAILY_GOAL_ANCHOR"],
    }


def daily_goal(parsed):
    """The goal dict features.performance reads, from parsed preferences."""
    return {
        "conversation_goal": int(parsed["DAILY_CONVERSATION_GOAL"]),
        "talk_minutes_goal": int(parsed["DAILY_GOAL_MINUTES"]),
        "minutes": int(parsed["DAILY_GOAL_MINUTES"]),
        "weekly_step": int(parsed["DAILY_GOAL_WEEKLY_STEP_MINUTES"]),
        "anchor": parsed["DAILY_GOAL_ANCHOR"],
    }


def save_goal(env_path, account_values, account_user_id, data, today, save_remote=None):
    """Save only the daily goal keys. A weekly step counts from an anchor date: today, whenever the goal changes."""
    signed_in = bool(account_user_id)
    current = values(env_path, account_values, signed_in=signed_in)
    minutes = data.get("daily_goal_minutes", data.get("daily_talk_goal_minutes", current.get("DAILY_GOAL_MINUTES")))
    conversations = data.get("daily_conversation_goal", current.get("DAILY_CONVERSATION_GOAL"))
    step = data.get("daily_goal_weekly_step", current.get("DAILY_GOAL_WEEKLY_STEP_MINUTES"))
    if isinstance(minutes, bool) or isinstance(step, bool) or isinstance(conversations, bool):
        raise ValueError("Daily goal values must be whole numbers.")
    same = (str(minutes).strip() == str(current.get("DAILY_GOAL_MINUTES") or "").strip()
            and str(conversations).strip() == str(current.get("DAILY_CONVERSATION_GOAL") or "").strip()
            and str(step).strip() == str(current.get("DAILY_GOAL_WEEKLY_STEP_MINUTES") or "").strip())
    anchor = current.get("DAILY_GOAL_ANCHOR") or ""
    if not same or not anchor:
        anchor = today.isoformat()
    candidate = {
        **current,
        "DAILY_GOAL_MINUTES": minutes,
        "DAILY_CONVERSATION_GOAL": conversations,
        "DAILY_GOAL_WEEKLY_STEP_MINUTES": step,
        "DAILY_GOAL_ANCHOR": anchor,
    }
    parsed = preferences(candidate)
    updates = {key: parsed[key] for key in ("DAILY_GOAL_MINUTES", "DAILY_CONVERSATION_GOAL", "DAILY_GOAL_WEEKLY_STEP_MINUTES")}
    updates["DAILY_GOAL_ANCHOR"] = parsed["DAILY_GOAL_ANCHOR"] if int(parsed["DAILY_GOAL_WEEKLY_STEP_MINUTES"]) > 0 else ""
    if signed_in:
        account_values.update(updates)
        if save_remote:
            save_remote(values(env_path, account_values, signed_in=True))
    else:
        write_env(env_path, updates)
    return {**parsed, **updates}


def save_settings(env_path, account_values, account_user_id, data, save_remote=None):
    signed_in = bool(account_user_id)
    existing = values(env_path, account_values, signed_in=signed_in)
    parsed = preferences({
        **existing,
        "DAILY_GOAL_MINUTES": data.get("daily_goal_minutes", existing.get("DAILY_GOAL_MINUTES")),
        "DAILY_GOAL_WEEKLY_STEP_MINUTES": data.get("daily_goal_weekly_step", existing.get("DAILY_GOAL_WEEKLY_STEP_MINUTES")),
        "DAILY_GOAL_ANCHOR": data.get("daily_goal_anchor", existing.get("DAILY_GOAL_ANCHOR")),
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
    current = values(env_path, account_values, signed_in=signed_in)
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
    if signed_in:
        account_values.update(updates)
        if save_remote:
            save_remote(values(env_path, account_values, signed_in=True))
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
