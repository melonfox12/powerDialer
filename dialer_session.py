"""Pure helpers for dialer stage, session accounting, and local-time rules."""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

STAGES = ("idle", "dialing", "ringing", "connected", "wrapup", "paused")
DISPOSITION_TO_STATUS = {
    "booked": "booked",
    "callback": "call",
    "not_interested": "disqualified",
    "no_answer": "call",
    "do_not_call": "disqualified",
}
TIMEZONE_NAMES = {
    "Eastern": "America/New_York",
    "Central": "America/Chicago",
    "Mountain": "America/Denver",
    "Pacific": "America/Los_Angeles",
    "Alaska": "America/Anchorage",
    "Hawaii": "Pacific/Honolulu",
}


def dialer_stage(running, paused, active, pending_outcome, in_flight):
    if not running:
        return "idle"
    if paused:
        return "paused"
    if pending_outcome:
        return "wrapup"
    if active:
        return "connected"
    if any(call.get("state") == "ringing" for call in in_flight):
        return "ringing"
    return "dialing"


def new_session(goal=20, started_at=None):
    started = started_at or datetime.now(timezone.utc).isoformat()
    return {
        "id": started,
        "started_at": started,
        "ended_at": None,
        "goal": int(goal),
        "dials": 0,
        "connects": 0,
        "conversations": 0,
        "meetings_booked": 0,
        "current_streak": 0,
        "best_streak": 0,
        "connect_times": [],
    }


def add_connect(session, timestamp=None):
    now = timestamp or datetime.now(timezone.utc)
    if isinstance(now, str):
        now = datetime.fromisoformat(now)
    times = [datetime.fromisoformat(value) for value in session.get("connect_times", [])]
    if times and now - times[-1] <= timedelta(minutes=10):
        session["current_streak"] = session.get("current_streak", 0) + 1
    else:
        session["current_streak"] = 1
    session["best_streak"] = max(session.get("best_streak", 0), session["current_streak"])
    times.append(now)
    cutoff = now - timedelta(minutes=10)
    session["connect_times"] = [value.isoformat() for value in times if value >= cutoff]
    session["connects"] = session.get("connects", 0) + 1


def recent_streak(session, now=None):
    instant = now or datetime.now(timezone.utc)
    if isinstance(instant, str):
        instant = datetime.fromisoformat(instant)
    cutoff = instant - timedelta(minutes=10)
    times = [datetime.fromisoformat(value) for value in session.get("connect_times", [])]
    return sum(value >= cutoff for value in times)


def local_time(timezone_name, now=None):
    zone_name = TIMEZONE_NAMES.get(str(timezone_name or "").strip(), timezone_name)
    if not zone_name or zone_name == "Unknown":
        return None
    try:
        zone = ZoneInfo(zone_name)
    except (ZoneInfoNotFoundError, TypeError):
        return None
    instant = now or datetime.now(timezone.utc)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    return instant.astimezone(zone)


def within_calling_window(timezone_name, start_hour=8, end_hour=21, now=None):
    local = local_time(timezone_name, now)
    if local is None:
        return False
    if not (0 <= start_hour <= 23 and 1 <= end_hour <= 24 and start_hour < end_hour):
        raise ValueError("Calling hours must be a valid, non-overlapping same-day range.")
    return time(start_hour) <= local.timetz().replace(tzinfo=None) < time(end_hour % 24)


def session_summary(session, ended_at=None):
    ended = ended_at or datetime.now(timezone.utc).isoformat()
    start = datetime.fromisoformat(session["started_at"])
    finish = datetime.fromisoformat(ended)
    result = dict(session)
    result["ended_at"] = ended
    result["duration_seconds"] = max(0, int((finish - start).total_seconds()))
    result.pop("connect_times", None)
    result.pop("current_streak", None)
    return result
