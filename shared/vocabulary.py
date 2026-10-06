"""Single definitions for statuses, dispositions, metrics, stages, timezones, and setting keys."""

import json

STATUSES = (
    {"key": "new", "label": "New", "color": "--muted", "className": "neutral"},
    {"key": "call", "label": "Callback", "color": "--amber", "className": "callback"},
    {"key": "booked", "label": "Booked", "color": "--success", "className": "positive"},
    {"key": "interested", "label": "Interested", "color": "--success", "className": "positive"},
    {"key": "disqualified", "label": "Not interested", "color": "--red", "className": "negative"},
    {"key": "do_not_call", "label": "Do not call", "color": "--red", "className": "negative"},
)
STATUS_KEYS = tuple(item["key"] for item in STATUSES)

DISPOSITION_TO_STATUS = {
    "booked": "booked",
    "callback": "call",
    "not_interested": "disqualified",
    "no_answer": "call",
    "do_not_call": "do_not_call",
}

OUTCOME_METRIC = {
    "call": "call_later",
    "interested": "interested",
    "booked": "booked",
}
DEFAULT_OUTCOME_METRIC = "disqualified"

METRIC_KEYS = (
    "booked",
    "call_later",
    "connected",
    "disqualified",
    "interested",
    "dials",
    "failed",
    "talk_seconds",
    "voicemail",
)

STAGES = ("idle", "dialing", "ringing", "connected", "wrapup", "paused")
CALL_STATES = ("creating", "calling agent", "ringing", "live", "cancelled", "ended", "skipped")

TIMEZONE_NAMES = {
    "Eastern": "America/New_York",
    "Central": "America/Chicago",
    "Mountain": "America/Denver",
    "Pacific": "America/Los_Angeles",
    "Alaska": "America/Anchorage",
    "Hawaii": "Pacific/Honolulu",
}
TIMEZONE_ALIASES = {
    "eastern": "Eastern", "est": "Eastern", "edt": "Eastern", "et": "Eastern",
    "america/new_york": "Eastern", "america/detroit": "Eastern", "america/indianapolis": "Eastern",
    "central": "Central", "cst": "Central", "cdt": "Central", "ct": "Central",
    "america/chicago": "Central",
    "mountain": "Mountain", "mst": "Mountain", "mdt": "Mountain", "mt": "Mountain",
    "america/denver": "Mountain", "america/phoenix": "Mountain",
    "pacific": "Pacific", "pst": "Pacific", "pdt": "Pacific", "pt": "Pacific",
    "america/los_angeles": "Pacific",
    "alaska": "Alaska", "akst": "Alaska", "akdt": "Alaska", "america/anchorage": "Alaska",
    "hawaii": "Hawaii", "hst": "Hawaii", "pacific/honolulu": "Hawaii",
}
UTC_OFFSET_ZONES = {-5: "Eastern", -6: "Central", -7: "Mountain", -8: "Pacific", -9: "Alaska", -10: "Hawaii"}

SETTING_DEFAULTS = {
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
SETTING_KEYS = tuple(SETTING_DEFAULTS)

TWILIO_ACCOUNT_KEYS = (
    "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN",
    "TWILIO_API_KEY",
    "TWILIO_API_SECRET",
    "TWILIO_TWIML_APP_SID",
    "PUBLIC_BASE_URL",
)
SUPABASE_ENV_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
)
REMOTE_SETTING_KEYS = TWILIO_ACCOUNT_KEYS + SETTING_KEYS
ENV_KEYS = TWILIO_ACCOUNT_KEYS + SUPABASE_ENV_KEYS + SETTING_KEYS
SETTINGS_ROW_ID = "app"

SECRET_INPUTS = (
    {"id": "authTokenInput", "label": "auth token"},
    {"id": "apiSecretInput", "label": "API key secret"},
)


def browser_vocabulary():
    return {
        "statuses": [dict(item) for item in STATUSES],
        "dispositions": dict(DISPOSITION_TO_STATUS),
        "outcomeMetric": dict(OUTCOME_METRIC),
        "defaultOutcomeMetric": DEFAULT_OUTCOME_METRIC,
        "metricKeys": list(METRIC_KEYS),
        "stages": list(STAGES),
        "callStates": list(CALL_STATES),
        "timezones": dict(TIMEZONE_NAMES),
        "settingKeys": list(SETTING_KEYS),
        "secretInputs": [dict(item) for item in SECRET_INPUTS],
    }


def vocabulary_json():
    return json.dumps(browser_vocabulary(), ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
