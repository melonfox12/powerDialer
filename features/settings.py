"""Preference validation, settings view, and env or account persistence."""

import json
from datetime import date

from shared.config import read_env, write_env
from shared.pipeline_config import (
    LOCKED_PIPELINE_KEYS,
    parse_custom_pipeline_steps_json,
)
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
        if key == "PIPELINE_CUSTOM_STEPS_JSON":
            raw = values.get(key)
            if raw is None:
                result[key] = ""
            elif isinstance(raw, str):
                result[key] = raw.strip()
            else:
                result[key] = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
            continue
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
    if result.get("PIPELINE_CUSTOM_STEPS_JSON"):
        _, err = parse_custom_pipeline_steps_json(result["PIPELINE_CUSTOM_STEPS_JSON"])
        if err:
            raise ValueError(err)
    return result


def values(env_path, account_values, *, signed_in):
    server = read_env(env_path)
    if signed_in:
        server = {key: "" if key in TWILIO_ACCOUNT_KEYS else value for key, value in server.items()}
    return {**server, **account_values}


def _pipeline_json_from_post(data):
    """Build PIPELINE_CUSTOM_STEPS_JSON from settings form POST."""
    raw = data.get("pipeline_custom_steps_json")
    if raw is not None:
        return str(raw).strip()
    steps = data.get("pipeline_custom_steps")
    if steps is None:
        return None
    if isinstance(steps, str):
        return steps.strip()
    if isinstance(steps, list):
        return json.dumps(steps, ensure_ascii=False, separators=(",", ":"))
    return ""


def settings_state(env_path, account_values, storage_name="local JSON files", account_email="", *, signed_in):
    current = values(env_path, account_values, signed_in=signed_in)
    parsed = preferences(current)
    tail, _ = parse_custom_pipeline_steps_json(parsed.get("PIPELINE_CUSTOM_STEPS_JSON") or "")
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
        "ai_bridge_wss_url": parsed.get("AI_BRIDGE_WSS_URL", ""),
        "ai_bridge_app_url": parsed.get("AI_BRIDGE_APP_URL", ""),
        "ai_bridge_secret": "",
        "has_ai_bridge_secret": bool(parsed.get("AI_BRIDGE_SECRET")),
        "cartesia_api_key": "",
        "has_cartesia_api_key": bool(parsed.get("CARTESIA_API_KEY")),
        "cartesia_voice_id": parsed.get("CARTESIA_VOICE_ID", ""),
        "openai_api_key": "",
        "has_openai_api_key": bool(parsed.get("OPENAI_API_KEY")),
        "ai_llm_model": parsed.get("AI_LLM_MODEL", "gpt-4o-mini"),
        "ai_bridge_embedded": parsed.get("AI_BRIDGE_EMBEDDED", "false").lower() == "true",
        "ai_voicemail_drop": parsed.get("AI_VOICEMAIL_DROP", "false").lower() == "true",
        "ai_voicemail_message": parsed.get("AI_VOICEMAIL_MESSAGE", ""),
        "daily_goal_minutes": int(parsed["DAILY_GOAL_MINUTES"]),
        "daily_conversation_goal": int(parsed["DAILY_CONVERSATION_GOAL"]),
        "daily_goal_weekly_step": int(parsed["DAILY_GOAL_WEEKLY_STEP_MINUTES"]),
        "daily_goal_anchor": parsed["DAILY_GOAL_ANCHOR"],
        "pipeline_custom_steps": tail,
        "pipeline_locked_step_keys": sorted(LOCKED_PIPELINE_KEYS),
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
    candidate = {
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
        "AI_BRIDGE_WSS_URL": str(data.get("ai_bridge_wss_url", existing.get("AI_BRIDGE_WSS_URL", ""))).strip(),
        "AI_BRIDGE_APP_URL": str(data.get("ai_bridge_app_url", existing.get("AI_BRIDGE_APP_URL", "http://127.0.0.1:8000"))).strip(),
        "AI_BRIDGE_SECRET": str(data.get("ai_bridge_secret", existing.get("AI_BRIDGE_SECRET", ""))).strip(),
        "CARTESIA_API_KEY": str(data.get("cartesia_api_key", existing.get("CARTESIA_API_KEY", ""))).strip(),
        "CARTESIA_VOICE_ID": str(data.get("cartesia_voice_id", existing.get("CARTESIA_VOICE_ID", ""))).strip(),
        "OPENAI_API_KEY": str(data.get("openai_api_key", existing.get("OPENAI_API_KEY", ""))).strip(),
        "AI_LLM_MODEL": str(data.get("ai_llm_model", existing.get("AI_LLM_MODEL", "gpt-4o-mini"))).strip(),
        "AI_BRIDGE_EMBEDDED": "true" if data.get("ai_bridge_embedded") else "false",
        "AI_VOICEMAIL_DROP": "true" if data.get("ai_voicemail_drop") else "false",
        "AI_VOICEMAIL_MESSAGE": str(data.get("ai_voicemail_message", existing.get("AI_VOICEMAIL_MESSAGE", ""))).strip(),
    }
    if "pipeline_custom_steps" in data or "pipeline_custom_steps_json" in data:
        pj = _pipeline_json_from_post(data)
        if pj is not None:
            candidate["PIPELINE_CUSTOM_STEPS_JSON"] = pj
    parsed = preferences(candidate)
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
    if not updates.get("AI_BRIDGE_SECRET"):
        updates["AI_BRIDGE_SECRET"] = current.get("AI_BRIDGE_SECRET", "")
    if not updates.get("CARTESIA_API_KEY"):
        updates["CARTESIA_API_KEY"] = current.get("CARTESIA_API_KEY", "")
    if not updates.get("OPENAI_API_KEY"):
        updates["OPENAI_API_KEY"] = current.get("OPENAI_API_KEY", "")
    if signed_in:
        account_values.update(updates)
        if save_remote:
            save_remote(values(env_path, account_values, signed_in=True))
    else:
        merged = write_env(env_path, updates)
        account_values.update(merged)
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
