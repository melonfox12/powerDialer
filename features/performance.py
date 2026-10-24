"""Performance page numbers. Pure functions over prospects, sessions and a clock: no storage, HTTP or I/O.

A call record is one `call_log` entry on a prospect (skipped rows are not dials).

**Dial** — any call_log row except ``answered_by == skipped``.

**Connect** — the agent was bridged to the prospect: ``connected`` is true on new rows
(``picked_up`` at hangup), or legacy rows with ``answered_by`` human/unknown and not voicemail,
no-answer, race_lost, etc.

**Conversation** — a connect with ``duration_seconds`` ≥ ``CONVERSATION_MIN_SECONDS`` (60) and not
voicemail. Talk time sums connected prospect seconds with the same voicemail exclusion.

Bookings are counted from `status_history` transitions into ``booked``. If a prospect is moved out
of Booked later they no longer contribute to booked totals or the chart (going forward). Each
prospect counts at most once, at their latest into-Booked transition while they remain Booked.
Backfilled rows use ``booked_at`` or the last dial time and are marked ``estimated``.
"""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from shared.vocabulary import (
    CALL_OUTCOME_KEYS,
    CONVERSATION_MIN_SECONDS,
    NOT_CONNECTED_CALL_ANSWERS,
    PERFORMANCE_RANGES,
    canonical_status,
    is_connected_call_log_entry,
)

NOT_CONNECTED_ANSWERS = NOT_CONNECTED_CALL_ANSWERS
SKIPPED_ANSWER = "skipped"
BOOKED_STATUS = "booked"


def is_connected_record(entry):
    """A connect is a dial where the agent was bridged to the prospect (picked up)."""
    return is_connected_call_log_entry(entry)


def parse_moment(value):
    try:
        moment = datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def local_zone(name):
    """The browser's IANA zone, or UTC when it is missing or unknown."""
    try:
        return ZoneInfo(str(name or ""))
    except (ValueError, OSError):
        return timezone.utc


def rate(numerator, denominator):
    """A 0 to 1 ratio, or None when there is nothing to divide by."""
    if not denominator:
        return None
    return numerator / denominator


def format_funnel_percent(value):
    """Whole numbers above 10%, one decimal below, dash when unknown."""
    if value is None or not isinstance(value, (int, float)) or not float("inf") > float(value) > float("-inf"):
        return "—"
    percent = value * 100
    if percent >= 10:
        return f"{round(percent)}%"
    return f"{percent:.1f}%"


def call_records(leads):
    records = []
    for lead in leads:
        for entry in lead.get("call_log") or []:
            if entry.get("answered_by") == SKIPPED_ANSWER:
                continue
            at = parse_moment(entry.get("started_at")) or parse_moment(entry.get("ended_at"))
            if at is None:
                continue
            connected = is_connected_record(entry)
            seconds = entry.get("duration_seconds")
            duration = int(seconds) if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0 else 0
            outcome = entry.get("outcome")
            records.append({
                "lead_id": lead.get("id"),
                "at": at,
                "connected": connected,
                "duration": duration,
                "answered_by": entry.get("answered_by") or "",
                "outcome": outcome if outcome in CALL_OUTCOME_KEYS else None,
            })
    records.sort(key=lambda record: record["at"])
    return records


def is_talk_time(record):
    return record["connected"] and record["answered_by"] != "voicemail"


def is_conversation(record, minimum_seconds=CONVERSATION_MIN_SECONDS):
    return is_talk_time(record) and record["duration"] >= minimum_seconds


def in_window(moment, start, end):
    return (start is None or moment >= start) and moment <= end


def status_history_for(lead, calls_by_lead=None):
    """Stored history plus a single estimated into-booked row when needed."""
    history = [dict(item) for item in (lead.get("status_history") or []) if isinstance(item, dict)]
    if any(item.get("to_status") == BOOKED_STATUS for item in history):
        return history
    if canonical_status(lead.get("status")) != BOOKED_STATUS:
        return history
    at = parse_moment(lead.get("booked_at"))
    if at is None and calls_by_lead:
        lead_calls = calls_by_lead.get(lead.get("id")) or []
        if lead_calls:
            at = max(item["at"] for item in lead_calls)
    if at is None:
        return history
    return history + [{
        "from_status": "unknown",
        "to_status": BOOKED_STATUS,
        "changed_at": at.isoformat(),
        "estimated": True,
    }]


def latest_into_booked(history):
    latest = None
    for entry in history:
        if entry.get("to_status") != BOOKED_STATUS:
            continue
        at = parse_moment(entry.get("changed_at"))
        if at is None:
            continue
        if latest is None or at > latest["at"]:
            latest = {"at": at, "estimated": bool(entry.get("estimated"))}
    return latest


def active_booking_moment(lead, calls_by_lead=None):
    """When this prospect counts as booked, or None if they are not Booked now."""
    if canonical_status(lead.get("status")) != BOOKED_STATUS:
        return None
    return latest_into_booked(status_history_for(lead, calls_by_lead))


def count_booked_in_pipeline(leads):
    """Prospects whose CRM status is Booked — the pipeline view."""
    return sum(1 for lead in leads if canonical_status(lead.get("status")) == BOOKED_STATUS)


def count_booked_from_history(leads, calls_by_lead=None):
    """Booked prospects using the same active-booking rule as Performance."""
    return sum(1 for lead in leads if active_booking_moment(lead, calls_by_lead) is not None)


def range_windows(range_key, now, zone):
    """(start, end) in UTC for day, week, or month ranges."""
    if range_key not in PERFORMANCE_RANGES:
        raise ValueError("Choose day, week, or month.")
    end = now.astimezone(timezone.utc)
    if range_key == "day":
        return end - timedelta(hours=24), end
    local_today = now.astimezone(zone).date()
    if range_key == "week":
        start_day = local_today - timedelta(days=6)
    else:
        start_day = local_today - timedelta(days=29)
    start = datetime.combine(start_day, time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, end


def window_counts(calls, leads, calls_by_lead, start, end):
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    connected = [call for call in chosen if call["connected"]]
    booked = 0
    for lead in leads:
        moment = active_booking_moment(lead, calls_by_lead)
        if moment and in_window(moment["at"], start, end):
            booked += 1
    return {
        "dials": len(chosen),
        "connected": len(connected),
        "conversations": sum(is_conversation(call) for call in connected),
        "talk_seconds": sum(call["duration"] for call in connected if is_talk_time(call)),
        "booked": booked,
    }


def funnel_rates(counts):
    return {
        "dials_to_connected": rate(counts["connected"], counts["dials"]),
        "connected_to_conversations": rate(counts["conversations"], counts["connected"]),
        "conversations_to_booked": rate(counts["booked"], counts["conversations"]),
    }


def today_bounds(now, zone):
    local_today = now.astimezone(zone).date()
    start = datetime.combine(local_today, time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, now.astimezone(timezone.utc)


def daily_totals(calls, leads, calls_by_lead, now, zone):
    start, end = today_bounds(now, zone)
    counts = window_counts(calls, leads, calls_by_lead, start, end)
    return {
        "conversations": counts["conversations"],
        "talk_seconds": counts["talk_seconds"],
        "talk_minutes": counts["talk_seconds"] / 60,
    }


def trend_buckets(calls, leads, calls_by_lead, range_key, start, end, now, zone):
    """Dials, conversations, and booked per hour (day) or per day (week/month)."""
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    grain = "hour" if range_key == "day" else "day"
    keys = []
    if grain == "hour":
        local_end = end.astimezone(zone).replace(minute=0, second=0, microsecond=0)
        for offset in range(23, -1, -1):
            keys.append((local_end - timedelta(hours=offset)).astimezone(timezone.utc))
    else:
        local_end = end.astimezone(zone).date()
        days = 7 if range_key == "week" else 30
        first_day = local_end - timedelta(days=days - 1)
        day = first_day
        while day <= local_end:
            keys.append(day)
            day += timedelta(days=1)

    buckets = []
    for key in keys:
        if grain == "hour":
            bucket_start = key
            bucket_end = key + timedelta(hours=1) - timedelta(microseconds=1)
            label = {"at": key.isoformat(), "hour": key.astimezone(zone).hour}
        else:
            bucket_start = datetime.combine(key, time.min, tzinfo=zone).astimezone(timezone.utc)
            bucket_end = datetime.combine(key, time.max, tzinfo=zone).astimezone(timezone.utc)
            label = {"date": key.isoformat(), "hour": None}
        bucket_calls = [call for call in chosen if in_window(call["at"], bucket_start, min(bucket_end, end))]
        connected = [call for call in bucket_calls if call["connected"]]
        booked = 0
        for lead in leads:
            moment = active_booking_moment(lead, calls_by_lead)
            if moment and in_window(moment["at"], bucket_start, min(bucket_end, end)):
                booked += 1
        buckets.append({
            **label,
            "dials": len(bucket_calls),
            "conversations": sum(is_conversation(call) for call in connected),
            "booked": booked,
        })
    return grain, buckets


def build_performance(leads, sessions, goal, range_key, tz_name, now, live_session_id=None):
    """JSON-ready payload for the simplified Performance page."""
    zone = local_zone(tz_name)
    calls = call_records(leads)
    calls_by_lead = {}
    for call in calls:
        calls_by_lead.setdefault(call["lead_id"], []).append(call)
    start, end = range_windows(range_key, now, zone)
    counts = window_counts(calls, leads, calls_by_lead, start, end)
    grain, buckets = trend_buckets(calls, leads, calls_by_lead, range_key, start, end, now.astimezone(timezone.utc), zone)
    today = daily_totals(calls, leads, calls_by_lead, now, zone)
    has_activity = counts["dials"] > 0 or counts["booked"] > 0 or any(
        bucket["dials"] or bucket["booked"] for bucket in buckets
    )
    return {
        "range": range_key,
        "timezone": getattr(zone, "key", "UTC"),
        "conversation_min_seconds": CONVERSATION_MIN_SECONDS,
        "has_activity": has_activity,
        "counts": counts,
        "funnel": funnel_rates(counts),
        "trend": {"grain": grain, "buckets": buckets},
        "daily": {
            "conversations": today["conversations"],
            "conversation_goal": int(goal.get("conversation_goal") or 20),
            "talk_minutes": today["talk_minutes"],
            "talk_minutes_goal": int(goal.get("talk_minutes_goal") or goal.get("minutes") or 60),
        },
        "pipeline_booked": count_booked_in_pipeline(leads),
        "metrics_booked": count_booked_from_history(leads, calls_by_lead),
    }
