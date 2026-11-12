"""Single definitions for statuses, dispositions, metrics, stages, timezones, and setting keys."""

import json

STATUSES = (
    {"key": "new", "label": "New", "color": "--muted", "className": "neutral"},
    {"key": "agent_use", "label": "Agent use", "color": "--muted", "className": "neutral"},
    {"key": "dialed", "label": "Dialed", "color": "--callback", "className": "callback"},
    {"key": "contact_engaged", "label": "Contact (engaged)", "color": "--blue", "className": "info"},
    {"key": "qualified", "label": "Qualified", "color": "--blue", "className": "info"},
    {"key": "booked", "label": "Booked", "color": "--success", "className": "positive"},
    {"key": "proposal_sent", "label": "Proposal sent", "color": "--success", "className": "positive"},
    {"key": "closed", "label": "Closed", "color": "--red", "className": "negative"},
)
STATUS_KEYS = tuple(item["key"] for item in STATUSES)
# CRM table, imports, and dialer (subset for in-call buttons: STATUS_CALL_OUTCOME).
CRM_STATUS_KEYS = STATUS_KEYS
CRM_STATUS_LABELS = {item["key"]: item["label"] for item in STATUSES}
# Statuses that no longer exist. A stored record that still carries one is read as the status that replaced it.
LEGACY_STATUSES = {
    "interested": "closed",
    "not_interested": "closed",
    "do_not_call": "closed",
    "call": "dialed",
    "send_info": "contact_engaged",
    "disqualified": "closed",
    "no_answer_disqualified": "closed",
}

# Never auto-dialed from the pool.
NEVER_DIAL_STATUSES = ("booked", "proposal_sent", "closed")
AGENT_USE_STATUS = "agent_use"
AGENT_RESERVED_NAME_FIELD = "agent_reserved_name"
AGENT_RESERVED_ID_FIELD = "agent_reserved_id"
AGENT_POOL_SIZE = 50
AI_AGENT_POOLS_JSON_KEY = "AI_AGENT_POOLS_JSON"
AI_AGENT_PLAYBOOKS_JSON_KEY = "AI_AGENT_PLAYBOOKS_JSON"

PLAYBOOK_TARGET_ROLES = ("receptionist", "decision_maker", "either")

VOICE_PROFILE_HUMAN_BROWSER = "human_browser"
VOICE_PROFILE_AI_CARTESIA = "cartesia_line"
VOICE_PROFILES = (VOICE_PROFILE_HUMAN_BROWSER, VOICE_PROFILE_AI_CARTESIA)

TRANSCRIPT_SOURCE_TWILIO = "twilio"
TRANSCRIPT_SOURCE_CARTESIA = "cartesia"
# Shown in CRM menus; agent_use is display-only for humans.
USER_SELECTABLE_CRM_STATUS_KEYS = tuple(
    key for key in STATUS_KEYS if key != AGENT_USE_STATUS
)
# Auto-dial pool modes on the Dialer (timezone filter stacks on top).
DIAL_POOL_STATUSES = ("new", "contact_engaged")
DEFAULT_DIAL_POOL_STATUS = "new"
DEFAULT_BUSINESS_TYPE = "pest control"
DIAL_BUSINESS_TYPE_OPTIONS = (
    {"key": "pest control", "label": "Pest control"},
    {"key": "hvac", "label": "HVAC"},
)
DIAL_BUSINESS_TYPE_KEYS = tuple(item["key"] for item in DIAL_BUSINESS_TYPE_OPTIONS)


def resolve_dial_business_type(value):
    """Map API or UI text to a dial-pool industry filter. Empty string means no filter."""
    text = str(value or "").strip()
    folded = text.casefold()
    if not folded or folded in ("all", "any"):
        return ""
    return text


def dial_business_type_label(key):
    folded = str(key or "").strip().casefold()
    for item in DIAL_BUSINESS_TYPE_OPTIONS:
        if item["key"].casefold() == folded:
            return item["label"]
    return str(key or "").strip()
DIAL_POOL_STATUS_LABELS = {"new": "New", "contact_engaged": "Contact (engaged)"}
# Five or more dials with no live contact → closed (dial-cap rule).
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
# CRM extra field: JSON array of {kind, at} marketing touch events (pipeline card timeline).
MARKETING_TOUCHES_FIELD = "Marketing touches"
# One-time backfill: Nov 5 dials + New + created that day → static Callback.
NOV5_2026_STATIC_CALLBACK_DATE = "2026-11-05"
NOV5_2026_STATIC_CALLBACK_MIGRATION_FLAG = "nov5_2026_static_callback_v2"
NOV5_2026_STATIC_CALLBACK_SETTING = "NOV5_2026_STATIC_CALLBACK_DONE"

DISPOSITION_TO_STATUS = {
    "booked": "booked",
    "callback": "dialed",
    "send_info": "contact_engaged",
    "not_interested": "closed",
    "no_answer": "dialed",
    "do_not_call": "closed",
}

# Metric buckets (legacy keys in metrics store).
OUTCOME_METRIC = {
    "dialed": "call_later",
    "contact_engaged": "interested",
    "qualified": "interested",
    "booked": "booked",
    "proposal_sent": "interested",
    "closed": "disqualified",
}
# In-call CRM buttons (subset of STATUS_KEYS).
STATUS_CALL_OUTCOME = {
    "dialed": "call_back",
    "contact_engaged": "send_info",
    "qualified": "send_info",
    "booked": "booked",
    "proposal_sent": "send_info",
    "closed": "not_interested",
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

# CRM pipeline kanban (Send info follow-up). Steps are fixed; spacing drives the ready timer.
PIPELINE_DIALED_STEP = "dialed"
PIPELINE_SEND_INFO_STEP = "call_1"
# Pipeline card status menu (subset of CRM statuses).
# Pipeline cards no longer show a status menu; status follows the column (synced in CRM).
PIPELINE_CRM_STATUS_KEYS = ()
PIPELINE_STEPS = (
    {"key": "dialed", "label": "Dialed", "wait_hours": 0},
    {"key": "call_1", "label": "Contacted (engaged)", "wait_hours": 0},
    {"key": "email_1", "label": "Email 1", "wait_hours": 36},
    {"key": "linkedin_add", "label": "LinkedIn add request", "wait_hours": 36},
    {"key": "call_2", "label": "Call 2", "wait_hours": 36},
    {"key": "email_2", "label": "Email 2", "wait_hours": 36},
    {"key": "linkedin_message", "label": "LinkedIn message", "wait_hours": 36},
    {"key": "call_3", "label": "Call 3", "wait_hours": 36},
    {"key": "email_3", "label": "Email 3", "wait_hours": 36},
    {"key": "any_channel", "label": "Any channel (every 60–90 days)", "wait_hours": 75 * 24},
)
PIPELINE_STEP_KEYS = tuple(item["key"] for item in PIPELINE_STEPS)
PIPELINE_FIRST_STEP = PIPELINE_STEP_KEYS[0]
PIPELINE_WAIT_BY_KEY = {item["key"]: item["wait_hours"] for item in PIPELINE_STEPS}


def pipeline_wait_hours(step_key):
    return PIPELINE_WAIT_BY_KEY.get(str(step_key or "").strip(), PIPELINE_WAIT_BY_KEY[PIPELINE_FIRST_STEP])


def pipeline_step_to_status(step_key):
    """CRM status for a prospect in this pipeline column (keys are stable; labels are UI)."""
    k = str(step_key or "").strip()
    if k == PIPELINE_DIALED_STEP:
        return "dialed"
    if k == PIPELINE_SEND_INFO_STEP:
        return "contact_engaged"
    return "qualified"

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
# The dialer picks a group independently of the prospect timezone filter.
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


def resolve_caller_id_group(key):
    parsed = str(key or "").strip().lower()
    return parsed if parsed in CALLER_ID_GROUPS else DEFAULT_CALLER_ID_GROUP


def caller_ids_for_group(key):
    return list(CALLER_ID_GROUPS[resolve_caller_id_group(key)]["caller_ids"])

SETTING_DEFAULTS = {
    "PIPELINE_CUSTOM_STEPS_JSON": "",
    "SESSION_GOAL": "20",
    "CONVERSATION_THRESHOLD_SECONDS": str(CONVERSATION_MIN_SECONDS),
    "AUTO_ADVANCE_DELAY_SECONDS": "3",
    "SOUNDS_ENABLED": "true",
    "SOUND_VOLUME": "35",
    "BREAK_NUDGE_MINUTES": "90",
    "CALLING_START_HOUR": "8",
    "CALLING_END_HOUR": "21",
    "OPENING_SCRIPT": "",
    "AI_AGENT_POOLS_JSON": "{}",
    "AI_AGENT_PLAYBOOKS_JSON": "{}",
    "AI_BRIDGE_WSS_URL": "",
    "AI_BRIDGE_APP_URL": "http://127.0.0.1:8000",
    "AI_BRIDGE_SECRET": "",
    "AI_BRIDGE_EMBEDDED": "false",
    "AI_BRIDGE_HOST": "0.0.0.0",
    "AI_BRIDGE_PORT": "8766",
    "CARTESIA_API_KEY": "",
    "CARTESIA_VOICE_ID": "",
    "OPENAI_API_KEY": "",
    "AI_LLM_MODEL": "gpt-4o-mini",
    "AI_VOICEMAIL_DROP": "false",
    "AI_VOICEMAIL_MESSAGE": "",
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
REMOTE_SETTING_KEYS = TWILIO_ACCOUNT_KEYS + SETTING_KEYS + ("PIPELINE_CUSTOM_STEPS_JSON",)
ENV_KEYS = TWILIO_ACCOUNT_KEYS + SUPABASE_ENV_KEYS + SETTING_KEYS
SETTINGS_ROW_ID = "app"

SECRET_INPUTS = (
    {"id": "authTokenInput", "label": "auth token"},
    {"id": "apiSecretInput", "label": "API key secret"},
    {"id": "aiBridgeSecretInput", "label": "bridge secret"},
    {"id": "openaiKeyInput", "label": "OpenAI key"},
    {"id": "cartesiaKeyInput", "label": "Cartesia key"},
)


_STATUS_LABEL_ALIASES = {
    "callback": "dialed",
    "callback (12 hour timer)": "dialed",
    "callback (2 hour timer)": "dialed",
    "send info": "contact_engaged",
    "contact (engaged)": "contact_engaged",
    "contacted (engaged)": "contact_engaged",
    "not interested": "closed",
    "do not call": "closed",
    "interested": "closed",
    "disqualified": "closed",
    "no answer (disqualified)": "closed",
    "call": "dialed",
    "send_info": "contact_engaged",
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


def agent_reserved_name(lead):
    fields = (lead or {}).get("fields") or {}
    direct = str((lead or {}).get(AGENT_RESERVED_NAME_FIELD) or fields.get(AGENT_RESERVED_NAME_FIELD) or "").strip()
    return direct


def agent_use_status_text(lead):
    """CRM label while a prospect is locked to an AI agent seat."""
    name = agent_reserved_name(lead)
    if name:
        return f"Agent {name} use"
    return CRM_STATUS_LABELS.get(AGENT_USE_STATUS, "Agent use")


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
        "userSelectableCrmStatusKeys": list(USER_SELECTABLE_CRM_STATUS_KEYS),
        "crmStatusLabels": dict(CRM_STATUS_LABELS),
        "agentUseStatus": AGENT_USE_STATUS,
        "agentReservedNameField": AGENT_RESERVED_NAME_FIELD,
        "agentReservedIdField": AGENT_RESERVED_ID_FIELD,
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
        "pipelineSteps": [dict(item) for item in PIPELINE_STEPS],
        "pipelineFirstStep": PIPELINE_FIRST_STEP,
        "pipelineDialedStep": PIPELINE_DIALED_STEP,
        "pipelineSendInfoStep": PIPELINE_SEND_INFO_STEP,
        "pipelineCrmStatusKeys": list(PIPELINE_CRM_STATUS_KEYS),
        "settingKeys": list(SETTING_KEYS),
        "secretInputs": [dict(item) for item in SECRET_INPUTS],
        "marketingTouchesField": MARKETING_TOUCHES_FIELD,
    }


def vocabulary_json():
    return json.dumps(browser_vocabulary(), ensure_ascii=True, separators=(",", ":")).replace("<", "\\u003c")
