"""Performance page numbers. Pure functions over prospects, sessions and a clock: no storage, HTTP or I/O.

A call record is one `call_log` entry on a prospect. `connected` and `outcome` are stored on new
entries; older entries have neither, so a legacy row counts as connected when a person answered.
A booking is a prospect with `booked_at`. A prospect marked booked before `booked_at` existed is
"undated": it is listed so the agent can date it, and it is not counted in any range.
"""

from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from shared.vocabulary import (
    CALL_OUTCOMES,
    CALL_OUTCOME_KEYS,
    CONVERSATION_MIN_SECONDS,
    DAILY_GOAL_MAX_MINUTES,
    HEATMAP_MIN_BUCKET_DIALS,
    HEATMAP_UNLOCK_DIALS,
    PERFORMANCE_RANGES,
    TREND_DAILY_LIMIT_DAYS,
)

LEGACY_CONNECTED_ANSWERS = ("human", "unknown")
SKIPPED_ANSWER = "skipped"
UNDATED_LIST_LIMIT = 50


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


def percent_change(current, previous):
    """Relative change as a ratio (0.25 is +25%), or None when it cannot be compared."""
    if current is None or previous is None or previous == 0:
        return None
    return (current - previous) / previous


def call_records(leads):
    records = []
    for lead in leads:
        for entry in lead.get("call_log") or []:
            if entry.get("answered_by") == SKIPPED_ANSWER:
                continue
            at = parse_moment(entry.get("started_at")) or parse_moment(entry.get("ended_at"))
            if at is None:
                continue
            connected = entry.get("connected")
            if not isinstance(connected, bool):
                connected = entry.get("answered_by") in LEGACY_CONNECTED_ANSWERS
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


def is_conversation(record, minimum_seconds=CONVERSATION_MIN_SECONDS):
    return record["connected"] and record["answered_by"] != "voicemail" and record["duration"] >= minimum_seconds


def booking_records(leads):
    """Dated bookings, and the prospects marked booked that have no date."""
    dated = []
    undated = []
    for lead in leads:
        at = parse_moment(lead.get("booked_at"))
        if at is not None:
            dated.append({"lead_id": lead.get("id"), "at": at})
        elif lead.get("status") == "booked":
            undated.append(lead)
    return dated, undated


def in_window(moment, start, end):
    return (start is None or moment >= start) and moment <= end


def range_windows(range_key, now, zone):
    """(start, end, previous_start, previous_end) in UTC. The previous window is as long as the current one.

    Today compares with the same hours of yesterday; 7 days compares with the 7 days before.
    All time has no start and no previous window.
    """
    if range_key not in PERFORMANCE_RANGES:
        raise ValueError("Choose today, 7d, or all.")
    now = now.astimezone(timezone.utc)
    if range_key == "all":
        return None, now, None, None
    local_today = now.astimezone(zone).date()
    back = 0 if range_key == "today" else 6
    start = datetime.combine(local_today - timedelta(days=back), time.min, tzinfo=zone).astimezone(timezone.utc)
    previous_start = datetime.combine(local_today - timedelta(days=2 * back + 1), time.min, tzinfo=zone).astimezone(timezone.utc)
    return start, now, previous_start, previous_start + (now - start)


def window_counts(calls, bookings, start, end):
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    connected = [call for call in chosen if call["connected"]]
    return {
        "dials": len(chosen),
        "connected": len(connected),
        "conversations": sum(is_conversation(call) for call in connected),
        "talk_seconds": sum(call["duration"] for call in connected),
        "booked": sum(in_window(booking["at"], start, end) for booking in bookings),
    }


def dialing_minutes(sessions, start, end, now, live_session_id=None):
    """Minutes inside [start, end] that fall in a dial session.

    A session with no end counts only when it is the live one; otherwise it was cut off and its length is unknown.
    """
    seconds = 0.0
    for session in sessions:
        began = parse_moment(session.get("started_at"))
        if began is None:
            continue
        finished = parse_moment(session.get("ended_at"))
        if finished is None:
            if session.get("id") != live_session_id:
                continue
            finished = now
        low = began if start is None else max(began, start)
        high = min(finished, end)
        if high > low:
            seconds += (high - low).total_seconds()
    return seconds / 60


def derived_metrics(counts):
    return {
        **counts,
        "connect_rate": rate(counts["connected"], counts["dials"]),
        "conversation_rate": rate(counts["conversations"], counts["connected"]),
        "booking_rate": rate(counts["booked"], counts["conversations"]),
        "avg_talk_seconds": rate(counts["talk_seconds"], counts["connected"]),
        "dials_per_meeting": rate(counts["dials"], counts["booked"]),
    }


def compared(current, previous, has_prior):
    """Each metric as {value, change}. change is None unless the previous window had dials."""
    result = {}
    for key, value in current.items():
        before = previous.get(key) if has_prior else None
        result[key] = {"value": value, "change": percent_change(value, before)}
    return result


def _monday(day):
    return day - timedelta(days=day.weekday())


def trend_buckets(calls, bookings, range_key, start, now, zone):
    """Connect rate, dials and bookings per hour (today), day (7 days) or day/week (all time)."""
    local_today = now.astimezone(zone).date()
    chosen = [call for call in calls if in_window(call["at"], start, now)]
    dated = [booking for booking in bookings if in_window(booking["at"], start, now)]
    if range_key == "all":
        moments = [item["at"] for item in chosen + dated]
        if not moments:
            return "day", []
        first = min(moments).astimezone(zone).date()
        grain = "day" if (local_today - first).days + 1 <= TREND_DAILY_LIMIT_DAYS else "week"
    else:
        grain = "hour" if range_key == "today" else "day"
        first = local_today - timedelta(days=0 if range_key == "today" else 6)

    def key_for(moment):
        local = moment.astimezone(zone)
        if grain == "hour":
            return (local.date(), local.hour)
        return (_monday(local.date()) if grain == "week" else local.date(), None)

    keys = []
    if grain == "hour":
        keys = [(local_today, hour) for hour in range(now.astimezone(zone).hour + 1)]
    else:
        day = _monday(first) if grain == "week" else first
        step = 7 if grain == "week" else 1
        while day <= local_today:
            keys.append((day, None))
            day += timedelta(days=step)
    buckets = {key: {"dials": 0, "connected": 0, "booked": 0} for key in keys}
    for call in chosen:
        bucket = buckets.get(key_for(call["at"]))
        if bucket is not None:
            bucket["dials"] += 1
            bucket["connected"] += call["connected"]
    for booking in dated:
        bucket = buckets.get(key_for(booking["at"]))
        if bucket is not None:
            bucket["booked"] += 1
    return grain, [
        {
            "date": day.isoformat(),
            "hour": hour,
            "dials": bucket["dials"],
            "connected": bucket["connected"],
            "rate": rate(bucket["connected"], bucket["dials"]),
            "booked": bucket["booked"],
        }
        for (day, hour), bucket in buckets.items()
    ]


def outcome_breakdown(calls, start, end):
    counts = Counter(
        call["outcome"] for call in calls
        if call["connected"] and call["outcome"] and in_window(call["at"], start, end)
    )
    tagged = sum(counts.values())
    return {
        "tagged": tagged,
        "items": [
            {"key": item["key"], "label": item["label"], "count": counts[item["key"]], "share": counts[item["key"]] / tagged}
            for item in CALL_OUTCOMES if counts[item["key"]]
        ],
    }


def heatmap(calls, start, end, zone):
    """Connect rate by weekday (Monday is 0) and local hour. Empty until enough dials exist."""
    chosen = [call for call in calls if in_window(call["at"], start, end)]
    result = {
        "unlocked": len(chosen) >= HEATMAP_UNLOCK_DIALS,
        "total_dials": len(chosen),
        "unlock_at": HEATMAP_UNLOCK_DIALS,
        "min_bucket_dials": HEATMAP_MIN_BUCKET_DIALS,
        "cells": [],
    }
    if not result["unlocked"]:
        return result
    buckets = {}
    for call in chosen:
        local = call["at"].astimezone(zone)
        counts = buckets.setdefault((local.weekday(), local.hour), [0, 0])
        counts[0] += 1
        counts[1] += call["connected"]
    result["cells"] = [
        {
            "weekday": weekday,
            "hour": hour,
            "dials": dials,
            "connects": connects,
            "rate": rate(connects, dials),
            "qualified": dials >= HEATMAP_MIN_BUCKET_DIALS,
        }
        for (weekday, hour), (dials, connects) in sorted(buckets.items())
    ]
    return result


def activity_days(calls, sessions, zone):
    """Local dates with at least one dial: a call record, or a session that dialed."""
    days = {call["at"].astimezone(zone).date() for call in calls}
    for session in sessions:
        began = parse_moment(session.get("started_at"))
        if began is not None and int(session.get("dials") or 0) > 0:
            days.add(began.astimezone(zone).date())
    return days


def streak(days, today):
    """Consecutive active days. It stays alive through today until the first dial of the day."""
    def run_ending(day):
        length = 0
        while day in days:
            length += 1
            day -= timedelta(days=1)
        return length

    active_today = today in days
    best = 0
    length = 0
    previous = None
    for day in sorted(days):
        length = length + 1 if previous is not None and day - previous == timedelta(days=1) else 1
        best = max(best, length)
        previous = day
    return {
        "current": run_ending(today if active_today else today - timedelta(days=1)),
        "best": best,
        "active_today": active_today,
    }


def daily_target(base_minutes, weekly_step, anchor, today):
    """Today's dial-block target: the base plus the weekly step for each full week since the anchor."""
    if weekly_step <= 0 or anchor is None or today < anchor:
        return base_minutes
    return min(base_minutes + weekly_step * ((today - anchor).days // 7), DAILY_GOAL_MAX_MINUTES)


def parse_anchor(value):
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None


def goal_progress(sessions, calls, goal, now, zone, live_session_id):
    local_today = now.astimezone(zone).date()
    day_start = datetime.combine(local_today, time.min, tzinfo=zone).astimezone(timezone.utc)
    target = daily_target(goal["minutes"], goal["weekly_step"], parse_anchor(goal["anchor"]), local_today)
    minutes = dialing_minutes(sessions, day_start, now, now, live_session_id)
    return {
        "target_minutes": target,
        "base_minutes": goal["minutes"],
        "weekly_step": goal["weekly_step"],
        "minutes_today": minutes,
        "reached": minutes >= target,
        **streak(activity_days(calls, sessions, zone), local_today),
    }


def undated_bookings(undated, calls_by_lead):
    rows = []
    for lead in undated[:UNDATED_LIST_LIMIT]:
        last = max((call["at"] for call in calls_by_lead.get(lead.get("id"), [])), default=None)
        rows.append({
            "id": lead.get("id"),
            "name": lead.get("name") or "",
            "business": lead.get("business") or "",
            "last_dial": last.isoformat() if last else "",
        })
    return rows


def build_performance(leads, sessions, goal, range_key, tz_name, now, live_session_id=None):
    """Everything the Performance page shows, as JSON-ready numbers.

    `goal` is {"minutes", "weekly_step", "anchor"} from the saved preferences.
    """
    zone = local_zone(tz_name)
    calls = call_records(leads)
    bookings, undated = booking_records(leads)
    start, end, previous_start, previous_end = range_windows(range_key, now, zone)
    current = window_counts(calls, bookings, start, end)
    previous = window_counts(calls, bookings, previous_start, previous_end) if previous_start else None
    has_prior = bool(previous and previous["dials"])
    now_utc = now.astimezone(timezone.utc)
    minutes = dialing_minutes(sessions, start, end, now_utc, live_session_id)
    metrics = derived_metrics(current)
    before = derived_metrics(previous) if previous else {}
    metrics["minutes_per_meeting"] = rate(minutes, current["booked"]) if minutes else None
    before["minutes_per_meeting"] = None
    grain, buckets = trend_buckets(calls, bookings, range_key, start, now_utc, zone)
    calls_by_lead = {}
    for call in calls:
        calls_by_lead.setdefault(call["lead_id"], []).append(call)
    return {
        "range": range_key,
        "timezone": getattr(zone, "key", "UTC"),
        "conversation_min_seconds": CONVERSATION_MIN_SECONDS,
        "has_dials": current["dials"] > 0,
        "metrics": compared(metrics, before, has_prior),
        "dialing_minutes": minutes,
        "trend": {"grain": grain, "buckets": buckets},
        "outcomes": outcome_breakdown(calls, start, end),
        "heatmap": heatmap(calls, None, now_utc, zone),
        "goal": goal_progress(sessions, calls, goal, now_utc, zone, live_session_id),
        "bookings": {"undated_count": len(undated), "undated": undated_bookings(undated, calls_by_lead)},
    }
