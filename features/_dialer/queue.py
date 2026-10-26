"""Session start, pause, stop, and manual dial. Imports calls, then slots, then timing."""

import secrets
import threading
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from features._dialer import calls, slots, timing
from features._dialer import projection, rules, twilio
from features._dialer.rules import new_session, session_summary
from shared.infra import utc_now
from shared.vocabulary import (
    DIAL_POOL_STATUS_LABELS,
    DIAL_POOL_STATUSES,
    caller_id_group_for_prospect_timezone,
    caller_ids_for_group,
    canonical_status,
    resolve_caller_id_group,
)

def maintain_crm(state):
    """CRM backfill and callback dial-list repair. Never call from GET /api/state or /api/live."""
    remember_open_skips(state)
    maybe_enforce_dial_caps(state)


def scan_crm(state):
    """Copy an open callback onto new prospects with the same name and location."""
    plan = calls.callback_sync_plan(state.crm.snapshot(), utc_now())
    synced = 0
    for item in plan:
        try:
            state.crm.set_status(item["id"], "call", item["scheduled_until"])
        except ValueError:
            continue
        synced += 1
    dial_caps = state.crm.enforce_dial_caps(repair_misclassified=True)
    if synced:
        noun = "prospect" if synced == 1 else "prospects"
        state.record_activity(f"Scan CRM synced {synced} {noun}", "web")
    repaired_new = dial_caps.get("to_new", 0)
    if repaired_new:
        noun = "prospect" if repaired_new == 1 else "prospects"
        state.record_activity(f"Reset {repaired_new} {noun} to New (wrong auto-disqualify)", "web")
    capped = dial_caps.get("capped", 0)
    if capped:
        noun = "prospect" if capped == 1 else "prospects"
        state.record_activity(f"Marked {capped} {noun} no answer (disqualified) (5+ dials)", "web")
    remember_open_skips(state)
    return {
        "synced": synced,
        "repaired": dial_caps,
        "no_answer_disqualified": capped,
        "disqualified": capped,
        "state": projection.public_state(state),
    }


def maybe_enforce_dial_caps(state):
    """Backfill dial-cap disqualifications at most once a minute while the app is open."""
    now = time.time()
    with state.lock:
        if now - state.dial_cap_enforced_at < 60:
            return 0
        state.dial_cap_enforced_at = now
    dial_caps = state.crm.enforce_dial_caps()
    capped = dial_caps.get("capped", 0)
    if capped:
        noun = "prospect" if capped == 1 else "prospects"
        state.record_activity(f"Marked {capped} {noun} no answer (disqualified) (5+ dials)", "web")
    return capped


def _caller_group_busy(state):
    with state.lock:
        return bool(state.in_flight or state.active or state.pending_outcome)


def _sync_caller_ids_to_prospect_timezone(state):
    key = resolve_caller_id_group(caller_id_group_for_prospect_timezone(state.selected_timezone))
    callers = caller_ids_for_group(key)
    with state.lock:
        current_key = resolve_caller_id_group(getattr(state, "caller_id_group", None))
        if current_key == key and list(state.callers) == callers:
            state.caller_id_group = key
            return
    if _caller_group_busy(state):
        raise ValueError("Finish or stop the current calls before changing the dial timezone.")
    with state.lock:
        state.caller_id_group = key
        state.callers = callers
        state.caller_index = 0


def set_pool_filters(state, timezone=None, pool_status=None):
    leads = state.crm.snapshot()
    timezone_changed = timezone is not None
    with state.lock:
        if timezone is not None:
            state.selected_timezone = str(timezone or "").strip() or None
        if pool_status is not None:
            parsed = canonical_status(pool_status)
            if parsed not in DIAL_POOL_STATUSES:
                raise ValueError("Dial pool status must be New or Send info.")
            state.dial_pool_status = parsed
        if state.session:
            state.queue_total = len(calls._pool_leads(state, leads))
        label = DIAL_POOL_STATUS_LABELS.get(state.dial_pool_status, state.dial_pool_status)
        zone = state.selected_timezone
        if zone:
            state.last_event = f"Dialing pool: {label} · {zone}"
        else:
            state.last_event = f"Dialing pool: {label} · all timezones"
        should_fill = state.running and state.agent_ready and not state.paused and not state.pending_outcome and not state.active
    if timezone_changed:
        _sync_caller_ids_to_prospect_timezone(state)
    if should_fill:
        slots.fill_slots(state)
    return projection.public_state(state)


def set_timezone_filter(state, timezone):
    return set_pool_filters(state, timezone=timezone)

def start(state, priority_lead_id=None):
    priority = calls._dialable_lead(state, priority_lead_id) if priority_lead_id else None
    with state.lock:
        if state.running:
            return projection.public_state(state)
        state.activity_log.clear()
        state.activity_sequence = 0
    state.record_activity("Start dialing request received", "web")
    raw = state.read_values()
    required = (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
        "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
    )
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError("Complete Twilio account credentials, API key, TwiML App, and public HTTPS URL in Settings.")
    public_url = raw["PUBLIC_BASE_URL"].rstrip("/")
    parsed = urllib.parse.urlsplit(public_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Public webhook URL must start with https://")
    values = state.read_settings()
    state.settings = values
    state.public_base_url = public_url
    _sync_caller_ids_to_prospect_timezone(state)
    callers = caller_ids_for_group(state.caller_id_group)
    state.record_activity(f"Twilio ready: {len(callers)} rotating caller ID(s)", "api")
    twilio.prepare_browser_voice(state, values)
    eligible = calls._pool_leads(state)
    if not eligible and priority is None:
        label = DIAL_POOL_STATUS_LABELS.get(state.dial_pool_status, "New")
        where = f" with {label} status"
        if state.selected_timezone:
            where += f" in the {state.selected_timezone} timezone"
        raise ValueError(f"There are no prospects ready to dial{where}. Prospects dialed recently stay out of the queue.")
    with state.lock:
        state.running = True
        state.paused = False
        state.agent_ready = False
        state.agent_call_uuid = None
        state.pending_outcome = None
        state.active = None
        state.in_flight.clear()
        calls._release_tokens(state)
        state.calls.clear()
        state.callers = callers
        state.caller_index = 0
        state.conference = "crm-" + secrets.token_hex(8)
        state.session = new_session(goal=int(values["SESSION_GOAL"]))
        state.taggable_call = None
        state.manual_lead_id = priority["id"] if priority else None
        state.queue_anchor_id = None
        pinned_extra = 1 if priority and all(item["id"] != priority["id"] for item in eligible) else 0
        state.queue_total = len(eligible) + pinned_extra
        state.advance_at = None
        state.advance_remaining = None
        rules._save_session(state)
        state.last_error = ""
        state.last_event = "Connecting computer audio"
        agent_call = calls._new_call(state, "agent", None)
        state.agent_call_token = agent_call["token"]
        slots._schedule_calling_window_check(state)
    rules._flush_metrics(state)
    view = projection.public_state(state)
    view["client_call_token"] = agent_call["token"]
    return view

def _current_queue_id(state, leads):
    with state.lock:
        active = state.active
        if active and active.get("kind") != "agent" and active.get("lead_id"):
            return active["lead_id"]
        if state.pending_outcome:
            return state.pending_outcome
        for call in state.in_flight.values():
            if call.get("kind") != "agent" and call.get("lead_id"):
                return call["lead_id"]
        manual = state.manual_lead_id
    if manual:
        return manual
    pool = calls._pool_leads(state, leads)
    return pool[0]["id"] if pool else ""

def drop_prospect_call(state, lead_id):
    """Hang up every line to this prospect.

    Returns (fill_now, schedule_advance). After a talked call, the queue resumes only when the
    auto-advance timer is scheduled; a line that never connected can refill immediately.
    """
    hung = []
    talked = False
    with state.lock:
        for token, call in list(state.in_flight.items()):
            if call.get("kind") == "agent" or call.get("lead_id") != lead_id:
                continue
            call["handled"] = True
            call["cancelled"] = True
            if call.get("picked_up"):
                talked = True
                call["outcome_chosen"] = True
            else:
                call["skip_closed"] = True
                call["state"] = "skipped"
            state.in_flight.pop(token, None)
            if state.active is call:
                state.active = None
            if call.get("call_uuid"):
                hung.append(call["call_uuid"])
        active = state.active
        if active and active.get("kind") != "agent" and active.get("lead_id") == lead_id:
            active["handled"] = True
            active["cancelled"] = True
            if active.get("picked_up"):
                talked = True
                active["outcome_chosen"] = True
            else:
                active["skip_closed"] = True
                active["state"] = "skipped"
            if active.get("call_uuid"):
                hung.append(active["call_uuid"])
            state.active = None
        if state.pending_outcome == lead_id:
            state.pending_outcome = None
        if state.manual_lead_id == lead_id:
            state.manual_lead_id = None
        if not talked:
            for call in state.calls.values():
                if call.get("lead_id") == lead_id and call.get("picked_up"):
                    talked = True
                    break
        rules.clear_stale_active(state)
        idle = (
            state.running and not state.paused and state.agent_ready
            and not state.active and not state.pending_outcome
        )
        should_fill = idle and not talked and not state.in_flight
        should_advance = idle and talked
    for call_uuid in hung:
        threading.Thread(target=twilio._hangup_call, args=(state, call_uuid), daemon=True).start()
    return should_fill, should_advance

def remember_skip(state, lead_id, when):
    moment = when.replace(microsecond=0).isoformat()
    try:
        state.crm.append_call_log(lead_id, {
            "id": f"skip-{lead_id}-{moment}",
            "started_at": moment,
            "ended_at": moment,
            "answered_by": "skipped",
        })
    except OSError as exc:
        state.record_activity(f"Could not log the skip: {exc}", "error")

def _has_dial_record(log, due):
    """True when the dial list already shows what started this callback: a skip, or a dial made around then."""
    floor = due - calls.CALLBACK_HOLD - timedelta(hours=1)
    for item in log:
        if item.get("answered_by") == "skipped":
            return True
        try:
            started = datetime.fromisoformat(str(item.get("started_at") or ""))
        except ValueError:
            continue
        if started.tzinfo is None:
            started = started.replace(tzinfo=timezone.utc)
        if started >= floor:
            return True
    return False

def remember_open_skips(state):
    """Keep an open callback that has no matching dial record in the dial list."""
    now = utc_now()
    for lead in state.crm.snapshot():
        if lead.get("status") != "call" or not lead.get("scheduled_until"):
            continue
        try:
            due = datetime.fromisoformat(str(lead["scheduled_until"]))
        except ValueError:
            continue
        if due.tzinfo is None:
            continue
        remaining = due - now
        if remaining <= timedelta(0) or remaining > calls.CALLBACK_HOLD:
            continue
        if _has_dial_record(lead.get("call_log") or [], due):
            continue
        remember_skip(state, lead["id"], due - calls.MANUAL_CALLBACK)

def schedule_callback(state, lead_id, scheduled_until=None, log_skip=True):
    """Set a manual callback (6 hours by default). log_skip adds the dial-list entry for it."""
    now = utc_now().replace(microsecond=0)
    due = scheduled_until or (now + calls.MANUAL_CALLBACK).isoformat()
    lead = state.crm.set_status(lead_id, "call", due)
    if log_skip:
        remember_skip(state, lead_id, now)
    return lead


def schedule_no_pickup_callback(state, lead_id):
    """After no pickup, set CRM to Callback with a 48-hour timer. Skips booked/disqualified and active callbacks."""
    lead = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    if lead is None or lead.get("status") != "new":
        return None
    due = (utc_now().replace(microsecond=0) + calls.NO_PICKUP_CALLBACK).isoformat()
    return state.crm.set_status(lead_id, "call", due)


def schedule_dropped_callback(state, lead_id):
    """Put a line we dropped (lost race, etc.) on the same no-pickup callback as a no-answer."""
    return schedule_no_pickup_callback(state, lead_id)

def pass_next(state, lead_id=None):
    lead_id = str(lead_id or "").strip() or _current_queue_id(state, state.crm.snapshot())
    if not lead_id:
        raise ValueError("There is no prospect to skip.")
    leads = state.crm.snapshot()
    lead = next((item for item in leads if item["id"] == lead_id), None)
    if lead is None:
        raise KeyError("Prospect not found")
    if lead.get("status") == "new":
        lead = schedule_callback(state, lead_id)
    else:
        remember_skip(state, lead_id, utc_now())
    with state.lock:
        if state.queue_anchor_id == lead_id:
            state.queue_anchor_id = None
    should_fill, should_advance = drop_prospect_call(state, lead_id)
    name = lead.get("name") or lead.get("business") or "Prospect"
    state.record_activity(f"Skipped {name}", "web")
    if should_fill:
        slots.fill_slots(state)
    elif should_advance:
        timing._schedule_advance(state)
    return projection.public_state(state)

def dial_lead(state, lead_id):
    lead = calls._dialable_lead(state, lead_id)
    name = lead.get("name") or lead.get("phone") or "Prospect"
    with state.lock:
        running = state.running
    if not running:
        view = start(state, priority_lead_id=lead["id"])
        if view.get("client_call_token"):
            view["dial_status"] = "started"
            state.record_activity(f"Manual dial started for {name}", "web")
            return view
    return _pin_manual_dial(state, lead, name)

def _pin_manual_dial(state, lead, name):
    with state.lock:
        on_line = (
            (state.active and state.active.get("lead_id") == lead["id"])
            or state.pending_outcome == lead["id"]
            or any(call.get("lead_id") == lead["id"] for call in state.in_flight.values())
        )
        if on_line:
            status = "already"
        else:
            state.manual_lead_id = lead["id"]
            if state.advance_timer:
                state.advance_timer.cancel()
                state.advance_timer = None
            state.advance_at = None
            state.advance_remaining = None
            idle = not state.active and not state.pending_outcome and not state.in_flight
            if state.paused and idle:
                state.paused = False
            status = "now" if state.agent_ready and not state.paused and idle else "next"
            if status == "next":
                state.last_event = f"Next dial: {name}"
    if status == "now":
        slots.fill_slots(state)
    view = projection.public_state(state)
    view["dial_status"] = status
    if status == "already":
        state.record_activity(f"Already dialing {name}", "web")
    else:
        state.record_activity(f"Manual dial {'placed' if status == 'now' else 'queued'} for {name}", "web")
    return view

def pause(state):
    with state.lock:
        if not state.running:
            return projection.public_state(state)
        state.paused = not state.paused
        state.last_event = "Paused" if state.paused else "Resumed"
        should_fill = not state.paused and state.agent_ready and not state.pending_outcome
        if state.paused and state.advance_timer:
            state.advance_remaining = max(0, state.advance_at - time.time()) if state.advance_at else 0
            state.advance_timer.cancel()
            state.advance_timer = None
            state.advance_at = None
            should_fill = False
        resume_countdown = not state.paused and state.advance_remaining is not None
        remaining = state.advance_remaining
        should_check_hours = not state.paused
        if state.paused and state.calling_window_timer:
            state.calling_window_timer.cancel()
            state.calling_window_timer = None
    if should_fill:
        slots.fill_slots(state)
    elif resume_countdown:
        timing._schedule_advance(state, remaining)
    if should_check_hours:
        slots._schedule_calling_window_check(state)
    return projection.public_state(state)

def stop(state):
    with state.lock:
        calls = list(state.calls.values())
        for call in calls:
            call["cancelled"] = True
        state.running = False
        state.paused = False
        state.agent_ready = False
        state.active = None
        state.pending_outcome = None
        state.manual_lead_id = None
        state.queue_anchor_id = None
        state.in_flight.clear()
        state.last_event = "Stopped"
        if state.advance_timer:
            state.advance_timer.cancel()
        state.advance_timer = None
        state.advance_at = None
        state.advance_remaining = None
        if state.calling_window_timer:
            state.calling_window_timer.cancel()
        state.calling_window_timer = None
        summary = session_summary(state.session) if state.session else None
        if summary:
            state.session.update(summary)
            rules._save_session(state)
    rules._flush_metrics(state)
    state.record_activity("Dialer stopped", "call")
    for call in calls:
        if call.get("call_uuid"):
            threading.Thread(target=twilio._hangup_call, args=(state, call["call_uuid"]), daemon=True).start()
    result = projection.public_state(state)
    if summary:
        result["session_summary"] = summary
        if state.metrics:
            result["previous_session"] = next(
                (item for item in state.metrics.recent_sessions(5) if item.get("id") != summary["id"]),
                None,
            )
    return result
