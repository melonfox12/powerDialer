"""Canonical top-level JSON keys for public HTTP responses.

Human-oriented field descriptions live in docs/ARCHITECTURE.md. Tests import
these tuples so the contract stays in one place.
"""

from typing import TypedDict

# --- Dialer snapshots (GET /api/state, nested "state" on mutations) ---

DIALER_STATE_KEYS = (
    "active_call_started_at",
    "active_lead",
    "active_lead_id",
    "activity_log",
    "advance_at",
    "agent_ready",
    "caller_ids",
    "caller_id_group",
    "counts",
    "current_caller_id",
    "dial_pool_status",
    "in_flight",
    "last_error",
    "last_event",
    "leads_version",
    "live_transcript",
    "manual_lead_id",
    "next_lead",
    "paused",
    "pending_outcome",
    "pending_outcome_id",
    "pickup_answered_by",
    "pool",
    "queue_count",
    "running",
    "selected_timezone",
    "session_stats",
    "settings",
    "stage",
    "tag_call",
    "timezone_groups",
)

LIVE_STATE_KEYS = tuple(key for key in DIALER_STATE_KEYS if key != "pool")

LEADS_CATALOG_KEYS = ("archived_dials", "counts", "dials_version", "leads", "leads_version", "pool", "timezone_groups")

DIALER_SETTINGS_KEYS = (
    "auto_advance_delay",
    "break_nudge_minutes",
    "calling_end_hour",
    "calling_start_hour",
    "conversation_threshold",
    "opening_script",
    "session_goal",
    "sound_volume",
    "sounds_enabled",
)

SETTINGS_VIEW_KEYS = (
    "account_email",
    "account_sid",
    "api_key",
    "api_secret",
    "auth_token",
    "auto_advance_delay",
    "break_nudge_minutes",
    "calling_end_hour",
    "calling_start_hour",
    "conversation_threshold",
    "daily_conversation_goal",
    "daily_goal_anchor",
    "daily_goal_minutes",
    "daily_goal_weekly_step",
    "has_api_secret",
    "has_auth_token",
    "opening_script",
    "public_base_url",
    "session_goal",
    "sound_volume",
    "sounds_enabled",
    "storage",
    "twiml_app_sid",
)

SESSION_STATS_KEYS = (
    "id",
    "started_at",
    "ended_at",
    "goal",
    "goal_reached_at",
    "dials",
    "connects",
    "conversations",
    "meetings_booked",
    "current_streak",
    "best_streak",
)

IN_FLIGHT_KEYS = ("answered_by", "caller_id", "lead", "lead_id", "name", "state")

LIVE_TRANSCRIPT_KEYS = ("answered_by", "lead_id", "lines", "partials", "transcribing")

ACTIVITY_LOG_ENTRY_KEYS = ("id", "message", "source", "timestamp")

COUNTS_KEYS = ("booked", "calling", "new", "total")

# --- CRM lead row (GET /api/leads → leads[], pool[], active_lead, etc.) ---

LEAD_KEYS = (
    "business",
    "fields",
    "id",
    "name",
    "phone",
    "scheduled_until",
    "status",
    "timezone",
    "transcript",
)

LEAD_OPTIONAL_KEYS = (
    "booked_at",
    "call_log",
    "passed_at",
    "status_history",
)

CALL_LOG_ENTRY_KEYS = (
    "answered_by",
    "caller_id",
    "connected",
    "duration_seconds",
    "ended_at",
    "id",
    "outcome",
    "started_at",
    "transcript_lines",
)

# --- Metrics bump store (GET /api/metrics) ---

METRICS_SNAPSHOT_KEYS = ("all_time", "daily", "today")

METRICS_DAILY_ROW_KEYS = ("booked", "connected", "date", "dials")

# --- Performance analytics (GET /api/performance) ---

PERFORMANCE_PAYLOAD_KEYS = (
    "conversation_min_seconds",
    "counts",
    "daily",
    "funnel",
    "has_activity",
    "metrics_booked",
    "pipeline_booked",
    "range",
    "timezone",
    "trend",
)

PERFORMANCE_DAILY_KEYS = (
    "conversation_goal",
    "conversations",
    "talk_minutes",
    "talk_minutes_goal",
)

PERFORMANCE_FUNNEL_KEYS = (
    "connected_to_booked",
    "connected_to_conversations",
    "conversations_to_booked",
    "dials_to_connected",
)

PERFORMANCE_COUNTS_KEYS = (
    "booked",
    "connected",
    "conversations",
    "dials",
    "talk_seconds",
)

PERFORMANCE_TREND_KEYS = ("buckets", "grain")

PERFORMANCE_TREND_BUCKET_KEYS = ("booked", "date", "dials", "hour", "pickups")


class LeadRecord(TypedDict, total=False):
    """Prospect row returned from the CRM catalog and embedded in dialer state."""

    id: str
    name: str
    business: str
    phone: str
    timezone: str
    status: str
    scheduled_until: str | None
    transcript: list
    fields: dict
    call_log: list
    booked_at: str | None
    passed_at: str | None
    status_history: list


class DialerStateResponse(TypedDict, total=False):
    """GET /api/state and nested state on POST mutations."""

    running: bool
    stage: str
    leads_version: int


def assert_top_level_keys(payload, keys):
    """Raise AssertionError when payload keys differ from the contract tuple."""
    if not isinstance(payload, dict):
        raise AssertionError(f"expected dict, got {type(payload).__name__}")
    expected = tuple(sorted(keys))
    actual = tuple(sorted(payload))
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        detail = []
        if missing:
            detail.append(f"missing {missing}")
        if extra:
            detail.append(f"extra {extra}")
        raise AssertionError("; ".join(detail))
