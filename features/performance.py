"""Performance page numbers. Pure functions over prospects, sessions and a clock: no storage, HTTP or I/O.

A call record is one `call_log` entry on a prospect (skipped rows are not dials).

**Dial** — any call_log row except ``answered_by == skipped``.

**Connect** — the agent was bridged to the prospect: ``connected`` is true on new rows
(``picked_up`` at hangup), or legacy rows with ``answered_by`` human/unknown and not voicemail,
no-answer, race_lost, etc.

**Conversation** — a dial with a transcript (``transcript_lines`` > 0 or matching lead segments), not
voicemail. Goal bars and the activity chart **pickups** series use this count per bucket (same rules
as Total dials transcript dials). Talk time sums connected seconds on transcript dials.

**Chart pickups** — per bucket, dials in that window where ``is_conversation`` is true (not raw
``connected``).

**Chart booked** — per bucket, dials in that window to prospects whose CRM status is ``booked``.

**Funnel** — ``dials_to_connected`` = connects ÷ dials; ``connected_to_conversations`` = conversations
÷ connects; ``conversations_to_booked`` = booked ÷ conversations. Booked uses prospects currently
Booked whose latest into-Booked transition falls in the range.

Goal-bar **talk time** sums connected seconds only on dials with ``transcript_lines`` > 0 in the
selected range (day / week / month uses the same window as the chart and funnel).

Bookings are counted from `status_history` transitions into ``booked``. If a prospect is moved out
of Booked later they no longer contribute to booked totals or the chart (going forward). Each
prospect counts at most once, at their latest into-Booked transition while they remain Booked.
Backfilled rows use ``booked_at`` or the last dial time and are marked ``estimated``.
"""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from shared.dial_policy import is_connected_call_log_entry
from shared.vocabulary import (
    CALL_OUTCOME_KEYS,
    CONVERSATION_MIN_SECONDS,
    NOT_CONNECTED_CALL_ANSWERS,
    DEFAULT_DAILY_CONVERSATION_GOAL,
    PERFORMANCE_RANGES,
    canonical_status,
)

NOT_CONNECTED_ANSWERS = NOT_CONNECTED_CALL_ANSWERS
SKIPPED_ANSWER = "skipped"
BOOKED_STATUS = "booked"
DAY_RANGE_HOURS = 12


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


def call_duration_seconds(entry):
    """Connected talk time for one call_log row (pickup through hangup)."""
    seconds = entry.get("duration_seconds")
    if isinstance(seconds, (int, float)) and not isinstance(seconds, bool) and seconds > 0:
        return int(seconds)
    start = parse_moment(entry.get("started_at"))
    end = parse_moment(entry.get("ended_at"))
    if start and end and end > start:
        return int((end - start).total_seconds())
    return 0


def dial_moment(entry):
    """When the dial counts for Total dials and Performance windows (ended, else started)."""
    return parse_moment(entry.get("ended_at")) or parse_moment(entry.get("started_at"))


def segments_for_dial(lead, entry):
    """Transcript lines on the lead that fall within this call_log row's time window."""
    start = parse_moment(entry.get("started_at"))
    if start is None:
        return []
    end = parse_moment(entry.get("ended_at"))
    slack = timedelta(seconds=45)
    matched = []
    for segment in lead.get("transcript") or []:
        moment = parse_moment(segment.get("timestamp"))
        if moment is None:
            continue
        if end is not None:
            if start - slack <= moment <= end + slack:
                matched.append(segment)
        elif moment >= start - slack:
            matched.append(segment)
    return matched


def transcript_talk_from_segments(segments):
    """Talk span from first to last transcript timestamp on this dial."""
    moments = [parse_moment(item.get("timestamp")) for item in segments]
    moments = [item for item in moments if item is not None]
    if len(moments) < 2:
        return 0
    return max(0, int((max(moments) - min(moments)).total_seconds()))


def effective_transcript_lines(lead, entry):
    stored = entry.get("transcript_lines")
    count = int(stored) if isinstance(stored, (int, float)) and not isinstance(stored, bool) else 0
    segments = segments_for_dial(lead, entry)
    return max(count, len(segments))


def live_connect_for_metrics(entry, transcript_lines):
    """Same intent as Total dials: live connect or a transcribed conversation."""
    if is_connected_record(entry):
        return True
    if transcript_lines <= 0:
        return False
    answered = str(entry.get("answered_by") or "")
    if answered in NOT_CONNECTED_ANSWERS or answered == "voicemail":
        return False
    return True


def call_records(leads):
    records = []
    for lead in leads:
        for entry in lead.get("call_log") or []:
            if entry.get("answered_by") == SKIPPED_ANSWER:
                continue
            at = dial_moment(entry)
            if at is None:
                continue
            segments = segments_for_dial(lead, entry)
            transcript_lines = effective_transcript_lines(lead, entry)
            connected = live_connect_for_metrics(entry, transcript_lines)
            seg_talk = transcript_talk_from_segments(segments)
            duration = seg_talk if seg_talk > 0 else call_duration_seconds(entry)
            outcome = entry.get("outcome")
            records.append({
                "lead_id": lead.get("id"),
                "at": at,
                "connected": connected,
                "duration": duration,
                "transcript_lines": max(0, transcript_lines),
                "answered_by": entry.get("answered_by") or "",
                "outcome": outcome if outcome in CALL_OUTCOME_KEYS else None,
            })
    records.sort(key=lambda record: record["at"])
    return records


def is_talk_time(record):
    return record["connected"] and record["answered_by"] != "voicemail"


def is_conversation(record):
    """Any dial in the period with a transcript (call_log count or lead segments), not voicemail."""
    if record.get("transcript_lines", 0) <= 0:
        return False
    return str(record.get("answered_by") or "") != "voicemail"


def leads_index(leads):
    return {str(lead.get("id")): lead for lead in leads if lead.get("id")}


def is_booked_lead_dial(call, leads_by_id):
    """Dial in range to a prospect whose CRM status is Booked (chart booked series)."""
    lead = leads_by_id.get(str(call.get("lead_id") or ""))
    if not lead:
        return False
    return canonical_status(lead.get("status")) == BOOKED_STATUS


def transcript_talk_seconds(record):
    """Talk time on transcript dials (segment span or connected duration)."""
    if record.get("transcript_lines", 0) <= 0:
        return 0
    if str(record.get("answered_by") or "") == "voicemail":
        return 0
    return record["duration"]


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
    """Day = rolling last ``DAY_RANGE_HOURS``; week/month = rolling windows ending at ``now``."""
    if range_key not in PERFORMANCE_RANGES:
        raise ValueError("Choose day, week, or month.")
    end = now.astimezone(timezone.utc)
    if range_key == "day":
        return end - timedelta(hours=DAY_RANGE_HOURS), end
    if range_key == "week":
        return end - timedelta(days=7), end
    return end - timedelta(days=30), end


def window_counts(calls, leads, calls_by_lead, start, end):
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    connected = [call for call in chosen if call["connected"]]
    leads_by_id = leads_index(leads)
    booked = sum(1 for call in chosen if is_booked_lead_dial(call, leads_by_id))
    return {
        "dials": len(chosen),
        "connected": len(connected),
        "conversations": sum(is_conversation(call) for call in chosen),
        "talk_seconds": sum(call["duration"] for call in connected if is_talk_time(call)),
        "booked": booked,
    }


def funnel_rates(counts):
    return {
        "dials_to_connected": rate(counts["connected"], counts["dials"]),
        "connected_to_conversations": rate(counts["conversations"], counts["connected"]),
        "conversations_to_booked": rate(counts["booked"], counts["conversations"]),
        "connected_to_booked": rate(counts["booked"], counts["connected"]),
    }


def trend_buckets(calls, leads, calls_by_lead, range_key, start, end, now, zone):
    """One bucket per hour (day) or per calendar day (week/month) from period start through end."""
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    grain = "hour" if range_key == "day" else "day"
    keys = []
    if grain == "hour":
        local_start = start.astimezone(zone).replace(minute=0, second=0, microsecond=0)
        local_end = end.astimezone(zone).replace(minute=0, second=0, microsecond=0)
        cursor = local_start
        while cursor <= local_end:
            keys.append(cursor.astimezone(timezone.utc))
            cursor += timedelta(hours=1)
    else:
        day = start.astimezone(zone).date()
        last_day = end.astimezone(zone).date()
        while day <= last_day:
            keys.append(day)
            day += timedelta(days=1)

    leads_by_id = leads_index(leads)
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
        pickups = sum(1 for call in bucket_calls if is_conversation(call))
        booked = sum(
            1 for call in bucket_calls
            if is_booked_lead_dial(call, leads_by_id)
        )
        buckets.append({
            **label,
            "dials": len(bucket_calls),
            "pickups": pickups,
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
    period_calls = [call for call in calls if in_window(call["at"], start, end)]
    period_connected = [call for call in period_calls if call["connected"]]
    goal_conversations = sum(is_conversation(call) for call in period_calls)
    goal_talk_seconds = sum(transcript_talk_seconds(call) for call in period_calls)
    has_activity = counts["dials"] > 0 or counts["booked"] > 0 or any(
        bucket["pickups"] or bucket["booked"] for bucket in buckets
    )
    return {
        "range": range_key,
        "timezone": getattr(zone, "key", "UTC"),
        "conversation_min_seconds": CONVERSATION_MIN_SECONDS,
        "has_activity": has_activity,
        "counts": counts,
        "funnel": funnel_rates(counts),
        "trend": {
            "grain": grain,
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "buckets": buckets,
        },
        "daily": {
            "range": range_key,
            "conversations": goal_conversations,
            "conversation_goal": int(goal.get("conversation_goal") or DEFAULT_DAILY_CONVERSATION_GOAL),
            "talk_minutes": goal_talk_seconds / 60,
            "talk_minutes_goal": int(goal.get("talk_minutes_goal") or goal.get("minutes") or 60),
        },
        "pipeline_booked": count_booked_in_pipeline(leads),
        "metrics_booked": count_booked_from_history(leads, calls_by_lead),
    }
