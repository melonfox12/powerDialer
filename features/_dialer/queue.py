"""Session start, pause, stop, and manual dial. Imports calls, then slots, then timing."""

import secrets
import threading
import time
import urllib.parse

from features._dialer import calls, slots, timing
from features._dialer import projection, session_stats, twilio_api
from features._dialer.session_stats import new_session, session_summary
from features.settings import preferences as _preferences
from features.settings import values as setting_values

def set_timezone_filter(state, timezone):
    timezone = str(timezone or "").strip() or None
    leads = state.crm.snapshot()
    with state.lock:
        state.selected_timezone = timezone
        if state.session:
            state.queue_total = len(calls._pool_leads(state, leads))
        state.last_event = f"Dialing pool set to {timezone}" if timezone else "Dialing pool set to all timezones"
        should_fill = state.running and state.agent_ready and not state.paused and not state.pending_outcome and not state.active
    if should_fill:
        slots.fill_slots(state)
    return projection.public_state(state)

def start(state, priority_lead_id=None):
    priority = calls._dialable_lead(state, priority_lead_id) if priority_lead_id else None
    with state.lock:
        if state.running:
            return projection.public_state(state)
        state.activity_log.clear()
        state.activity_sequence = 0
    state.record_activity("Start dialing request received", "web")
    values = setting_values(state)
    required = (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
        "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("Complete Twilio account credentials, API key, TwiML App, and public HTTPS URL in Settings.")
    public_url = values["PUBLIC_BASE_URL"].rstrip("/")
    parsed = urllib.parse.urlsplit(public_url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("Public webhook URL must start with https://")
    preferences = _preferences(values)
    state.settings = {**values, **preferences}
    state.public_base_url = public_url
    state.record_activity("Checking Twilio account for voice-capable caller IDs", "api")
    numbers = twilio_api.twilio_request(values["TWILIO_ACCOUNT_SID"], values["TWILIO_AUTH_TOKEN"],
                             "GET", "/IncomingPhoneNumbers.json", params={"PageSize": 1000})
    callers = []
    for item in numbers.get("incoming_phone_numbers", []):
        if not item.get("capabilities", {}).get("voice", False):
            continue
        caller = twilio_api.normalize_phone(item.get("phone_number", ""))
        if caller and caller not in callers:
            callers.append(caller)
    if not callers:
        raise ValueError("No voice-enabled Twilio phone numbers were found on this account.")
    state.record_activity(f"Twilio ready: {len(callers)} caller ID(s) available", "api")
    eligible = calls._pool_leads(state)
    if not eligible and priority is None:
        where = f" in the {state.selected_timezone} timezone" if state.selected_timezone else ""
        raise ValueError(f"There are no prospects with new status{where} in the caller pool.")
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
        state.session = new_session(goal=int(preferences["SESSION_GOAL"]))
        state.manual_lead_id = priority["id"] if priority else None
        pinned_extra = 1 if priority and all(item["id"] != priority["id"] for item in eligible) else 0
        state.queue_total = len(eligible) + pinned_extra
        state.advance_at = None
        state.advance_remaining = None
        session_stats._save_session(state)
        state.last_error = ""
        state.last_event = "Connecting computer audio"
        agent_call = calls._new_call(state, "agent", None)
        state.agent_call_token = agent_call["token"]
        slots._schedule_calling_window_check(state)
    view = projection.public_state(state)
    view["client_call_token"] = agent_call["token"]
    return view

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
            session_stats._save_session(state)
    state.record_activity("Dialer stopped", "call")
    for call in calls:
        if call.get("call_uuid"):
            threading.Thread(target=twilio_api._hangup_call, args=(state, call["call_uuid"]), daemon=True).start()
    result = projection.public_state(state)
    if summary:
        result["session_summary"] = summary
        if state.metrics:
            result["previous_session"] = next(
                (item for item in state.metrics.recent_sessions(5) if item.get("id") != summary["id"]),
                None,
                ) if hasattr(state.metrics, "recent_sessions") else None
    return result
