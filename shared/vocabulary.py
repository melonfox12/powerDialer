"""Single definitions for statuses, dispositions, metrics, stages, timezones, and setting keys."""

import json

STATUSES = (
    {"key": "new", "label": "New", "color": "--muted", "className": "neutral"},
    {"key": "call", "label": "Callback", "color": "--amber", "className": "callback"},
    {"key": "send_info", "label": "Send info", "color": "--blue", "className": "info"},
    {"key": "booked", "label": "Booked", "color": "--success", "className": "positive"},
    {"key": "disqualified", "label": "Disqualified", "color": "--red", "className": "negative"},
    {"key": "no_answer_disqualified", "label": "No answer (disqualified)", "color": "--red", "className": "no-answer-dq"},
)
STATUS_KEYS = tuple(item["key"] for item in STATUSES)
# CRM table and add-prospect menus (dialer outcome buttons use STATUS_CALL_OUTCOME only).
CRM_STATUS_KEYS = ("new", "call", "send_info", "booked", "disqualified", "no_answer_disqualified")
CRM_STATUS_LABELS = {
    "new": "New",
    "call": "Callback",
    "send_info": "Send info",
    "booked": "Booked",
    "disqualified": "Disqualified",
    "no_answer_disqualified": "No answer (disqualified)",
}
# Statuses that no longer exist. A stored record that still carries one is read as the status that replaced it.
LEGACY_STATUSES = {
    "interested": "disqualified",
    "not_interested": "disqualified",
    "do_not_call": "disqualified",
}

# A prospect in one of these statuses never goes back to "new" or "call" and is never dialed.
NEVER_DIAL_STATUSES = ("booked", "disqualified", "no_answer_disqualified")
# Auto-dial pool modes on the Dialer (timezone filter stacks on top).
DIAL_POOL_STATUSES = ("new", "send_info")
DEFAULT_DIAL_POOL_STATUS = "new"
DEFAULT_BUSINESS_TYPE = "pest control"
DIAL_BUSINESS_TYPE_OPTIONS = (
    {"key": "pest control", "label": "Pest control"},
    {"key": "hvac", "label": "HVAC"},
)
DIAL_BUSINESS_TYPE_KEYS = tuple(item["key"] for item in DIAL_BUSINESS_TYPE_OPTIONS)


def resolve_dial_business_type(value):
    """Map API or UI text to a dial-pool business type filter. Empty string means no filter."""
    folded = str(value or "").strip().casefold()
    if not folded or folded in ("all", "any"):
        return ""
    for key in DIAL_BUSINESS_TYPE_KEYS:
        if key.casefold() == folded:
            return key
    return ""


def dial_business_type_label(key):
    folded = str(key or "").strip().casefold()
    for item in DIAL_BUSINESS_TYPE_OPTIONS:
        if item["key"].casefold() == folded:
            return item["label"]
    return str(key or "").strip()
DIAL_POOL_STATUS_LABELS = {"new": "New", "send_info": "Send info"}
# Five or more dials with no live contact → no_answer_disqualified (not sales disqualified).
NO_ANSWER_DISQUALIFY_MIN_DIALS = 5
# Back-compat name for imports/tests that referenced the old cap constant.
MAX_DIAL_ATTEMPTS_BEFORE_DISQUALIFY = NO_ANSWER_DISQUALIFY_MIN_DIALS

LEGACY_CONNECTED_ANSWERS = ("human", "unknown")
NOT_CONNECTED_CALL_ANSWERS = (
    "no_answer",
    "voicemail",
    "skipped",
    "race_lost",
    "cancelled",
    "dead_line",
)
# Connect, pool, and cap rules: shared.dial_policy (imports these constants).
# Callback status (manual disposition, CRM button, or no-pickup drop) comes due after this long.
MANUAL_CALLBACK_HOURS = 2
NO_PICKUP_CALLBACK_HOURS = 2
LEGACY_NO_PICKUP_CALLBACK_HOURS = 48
CALLBACK_TIMER_MIGRATION_SHIFT_HOURS = LEGACY_NO_PICKUP_CALLBACK_HOURS - NO_PICKUP_CALLBACK_HOURS
# Legacy name kept for imports; automatic no-pickup callbacks use NO_PICKUP_CALLBACK_HOURS.
DROPPED_CALLBACK_MINUTES = NO_PICKUP_CALLBACK_HOURS * 60
CALLBACK_TIMER_MIGRATION_FIELD = "callback_timer_48h_to_2h"

DISPOSITION_TO_STATUS = {
    "booked": "booked",
    "callback": "call",
    "send_info": "send_info",
    "not_interested": "disqualified",
    "no_answer": "call",
    "do_not_call": "disqualified",
}

# Send info is the interested signal: that counter keeps its stored name.
OUTCOME_METRIC = {
    "call": "call_later",
    "send_info": "interested",
    "booked": "booked",
}
# The tag each status button leaves on the call it ended.
STATUS_CALL_OUTCOME = {
    "call": "call_back",
    "send_info": "send_info",
    "booked": "booked",
    "disqualified": "not_interested",
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

# Performance page. A conversation is a connected call at least this long.
CONVERSATION_MIN_SECONDS = 30
# Tags the agent puts on a connected call. "booked" also marks the prospect booked.
CALL_OUTCOMES = (
    {"key": "not_interested", "label": "Disqualified"},
    {"key": "gatekeeper", "label": "Gatekeeper"},
    {"key": "send_info", "label": "Send info"},
    {"key": "call_back", "label": "Call back"},
    {"key": "booked", "label": "Booked"},
)
CALL_OUTCOME_KEYS = tuple(item["key"] for item in CALL_OUTCOMES)
PERFORMANCE_RANGES = ("day", "week", "month")
DEFAULT_PERFORMANCE_RANGE = "week"
DEFAULT_DAILY_CONVERSATION_GOAL = 30
DEFAULT_DAILY_TALK_GOAL_MINUTES = 60
# Connect-rate heatmap: hidden below the unlock count, and a cell is muted below the bucket minimum.
HEATMAP_UNLOCK_DIALS = 100
HEATMAP_MIN_BUCKET_DIALS = 10
DAILY_GOAL_MAX_MINUTES = 720
# Beyond this many days the all-time trend groups by week.
TREND_DAILY_LIMIT_DAYS = 84

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

# Rotating outbound caller IDs grouped by the timezone they represent.
CALLER_ID_GROUP_KEYS = ("eastern", "central", "mountain", "pacific")
DEFAULT_CALLER_ID_GROUP = "eastern"
CALLER_ID_GROUPS = {
    "eastern": {
        "label": "Eastern",
        "caller_ids": ("+18607354163", "+18607521887", "+18607824999"),
    },
    "central": {
        "label": "Central",
        "caller_ids": ("+19206545904", "+19207827371", "+19205668506"),
    },
    "mountain": {
        "label": "Mountain",
        "caller_ids": ("+15055602960", "+15053995221", "+15053703413"),
    },
    "pacific": {
        "label": "Pacific",
        "caller_ids": ("+12136953093", "+12139533359", "+12137204625"),
    },
}


PROSPECT_TIMEZONE_TO_CALLER_ID_GROUP = {
    "Eastern": "eastern",
    "Central": "central",
    "Mountain": "mountain",
    "Pacific": "pacific",
    "Alaska": "mountain",
    "Hawaii": "pacific",
}


def resolve_caller_id_group(key):
    parsed = str(key or "").strip().lower()
    return parsed if parsed in CALLER_ID_GROUPS else DEFAULT_CALLER_ID_GROUP


def caller_id_group_for_prospect_timezone(timezone_name):
    zone = str(timezone_name or "").strip()
    if not zone:
        return DEFAULT_CALLER_ID_GROUP
    return PROSPECT_TIMEZONE_TO_CALLER_ID_GROUP.get(zone, DEFAULT_CALLER_ID_GROUP)


def caller_ids_for_group(key):
    return list(CALLER_ID_GROUPS[resolve_caller_id_group(key)]["caller_ids"])

SETTING_DEFAULTS = {
    "SESSION_GOAL": "20",
    "CONVERSATION_THRESHOLD_SECONDS": str(CONVERSATION_MIN_SECONDS),
    "AUTO_ADVANCE_DELAY_SECONDS": "3",
    "SOUNDS_ENABLED": "true",
    "SOUND_VOLUME": "35",
    "BREAK_NUDGE_MINUTES": "90",
    "CALLING_START_HOUR": "8",
    "CALLING_END_HOUR": "21",
    "OPENING_SCRIPT": "",
    "DAILY_GOAL_MINUTES": "60",
    "DAILY_CONVERSATION_GOAL": "30",
    # 0 turns the weekly increase off. The anchor is the local date the goal was last set.
    "DAILY_GOAL_WEEKLY_STEP_MINUTES": "0",
    "DAILY_GOAL_ANCHOR": "",
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


_STATUS_LABEL_ALIASES = {
    "callback": "call",
    "callback (12 hour timer)": "call",
    "callback (2 hour timer)": "call",
    "send info": "send_info",
    "not interested": "disqualified",
    "do not call": "disqualified",
    "interested": "disqualified",
    "no answer (disqualified)": "no_answer_disqualified",
}


def parse_prospect_status(value):
    """Map API, CSV, or UI text to a STATUS_KEYS value. Returns None when it cannot."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text in STATUS_KEYS:
        return text
    if text in LEGACY_STATUSES:
        return LEGACY_STATUSES[text]
    folded = text.casefold()
    if folded in _STATUS_LABEL_ALIASES:
        return _STATUS_LABEL_ALIASES[folded]
    for key, label in CRM_STATUS_LABELS.items():
        if label.casefold() == folded:
            return key
    for item in STATUSES:
        if item["label"].casefold() == folded:
            return item["key"]
    return LEGACY_STATUSES.get(text)


def canonical_status(status):
    """The current status for a stored one. Missing or unknown labels read as new when possible."""
    if status is None:
        return "new"
    text = str(status).strip()
    if not text:
        return "new"
    parsed = parse_prospect_status(text)
    if parsed in STATUS_KEYS:
        return parsed
    return "new"


def browser_vocabulary():
    return {
        "statuses": [dict(item) for item in STATUSES],
        "crmStatusKeys": list(CRM_STATUS_KEYS),
        "crmStatusLabels": dict(CRM_STATUS_LABELS),
        "neverDialStatuses": list(NEVER_DIAL_STATUSES),
        "dialPoolStatuses": list(DIAL_POOL_STATUSES),
        "dialPoolStatusLabels": dict(DIAL_POOL_STATUS_LABELS),
        "defaultDialPoolStatus": DEFAULT_DIAL_POOL_STATUS,
        "dialBusinessTypeOptions": [dict(item) for item in DIAL_BUSINESS_TYPE_OPTIONS],
        "dispositions": dict(DISPOSITION_TO_STATUS),
        "outcomeMetric": dict(OUTCOME_METRIC),
        "defaultOutcomeMetric": DEFAULT_OUTCOME_METRIC,
        "metricKeys": list(METRIC_KEYS),
        "callOutcomes": [dict(item) for item in CALL_OUTCOMES],
        "performanceRanges": list(PERFORMANCE_RANGES),
        "defaultPerformanceRange": DEFAULT_PERFORMANCE_RANGE,
        "conversationMinSeconds": CONVERSATION_MIN_SECONDS,
        "defaultDailyConversationGoal": DEFAULT_DAILY_CONVERSATION_GOAL,
        "defaultDailyTalkGoalMinutes": DEFAULT_DAILY_TALK_GOAL_MINUTES,
        "heatmapUnlockDials": HEATMAP_UNLOCK_DIALS,
        "heatmapMinBucketDials": HEATMAP_MIN_BUCKET_DIALS,
        "stages": list(STAGES),
        "callStates": list(CALL_STATES),
        "timezones": dict(TIMEZONE_NAMES),
        "callerIdGroups": [
            {"key": key, "label": CALLER_ID_GROUPS[key]["label"]} for key in CALLER_ID_GROUP_KEYS
        ],
        "defaultCallerIdGroup": DEFAULT_CALLER_ID_GROUP,
        "callbackStatusHours": NO_PICKUP_CALLBACK_HOURS,
        "settingKeys": list(SETTING_KEYS),
        "secretInputs": [dict(item) for item in SECRET_INPUTS],
    }


def vocabulary_json():
    return json.dumps(browser_vocabulary(), ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
