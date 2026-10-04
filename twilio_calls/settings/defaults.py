import json
import os

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
