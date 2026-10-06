"""Start, manual dial, caller rotation, and pause or stop."""

import secrets
import threading
import time
import urllib.parse

from features._dialer._queue import slots, timing
from features._dialer.session_stats import new_session, session_summary
from features._dialer import twilio_api
from features.settings import preferences as _preferences

def _pool_leads(state, leads=None):
    leads = state.crm.snapshot() if leads is None else leads
    pool = [lead for lead in leads if lead["status"] == "new"]
    if state.selected_timezone:
        pool = [lead for lead in pool if (lead.get("timezone") or "Unknown") == state.selected_timezone]
    return pool

def set_timezone_filter(state, timezone):
    timezone = str(timezone or "").strip() or None
    leads = state.crm.snapshot()
    with state.lock:
        state.selected_timezone = timezone
        if state.session:
            state.queue_total = len(state._pool_leads(leads))
        state.last_event = f"Dialing pool set to {timezone}" if timezone else "Dialing pool set to all timezones"
        should_fill = state.running and state.agent_ready and not state.paused and not state.pending_outcome and not state.active
    if should_fill:
        state.fill_slots()
    return state.public_state()

def _next_caller(state):
    with state.lock:
        if not state.callers:
            raise twilio_api.TwilioError("No voice-enabled Twilio numbers are available.")
        caller = state.callers[state.caller_index % len(state.callers)]
        state.caller_index += 1
        return caller

def _launch_call(state, call, destination):
    if not call.get("caller_id"):
        call["caller_id"] = state._next_caller()
    threading.Thread(target=state._create_call, args=(call, destination), daemon=True).start()

def _create_call(state, call, destination):
    caller = call.get("caller_id") or state._next_caller()
    call["caller_id"] = caller
    data = {
        "To": destination,
        "From": caller,
        "Url": state._url(call, "answer"),
        "Method": "GET",
        "StatusCallback": state._url(call, "status"),
        "StatusCallbackMethod": "POST",
        "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
        "Timeout": "25",
        "TimeLimit": "14400",
    }
    if call["kind"] == "prospect":
        data.update({
            "MachineDetection": "Enable",
            "AsyncAmd": "true",
            "MachineDetectionTimeout": "12",
            "MachineDetectionSpeechEndThreshold": "800",
            "AsyncAmdStatusCallback": state._url(call, "machine"),
            "AsyncAmdStatusCallbackMethod": "POST",
        })
    lead_name = (call.get("lead") or {}).get("name") or "prospect"
    state.record_activity(f"Requesting Twilio call for {lead_name}", "api")
    try:
        result = twilio_api.twilio_request(state.settings["TWILIO_ACCOUNT_SID"], state.settings["TWILIO_AUTH_TOKEN"],
                                "POST", "/Calls.json", data=data)
        call_uuid = result.get("sid")
        if not call_uuid:
            raise twilio_api.TwilioError("Twilio did not return a call SID.")
        with state.lock:
            call["call_uuid"] = call_uuid
            if call["kind"] == "agent":
                state.agent_call_uuid = call_uuid
            cancelled = call["cancelled"]
            if not cancelled:
                state.last_event = "Ringing agent" if call["kind"] == "agent" else "Calling prospects"
        if cancelled:
            state._hangup_call(call_uuid)
        else:
            state.record_activity(f"Twilio call accepted for {lead_name}", "call")
    except twilio_api.TwilioError as exc:
        with state.lock:
            if call["kind"] == "agent":
                state.running = False
            else:
                state.in_flight.pop(call["token"], None)
                call["handled"] = True
                state._bump("failed")
            state.paused = True
            state.last_error = str(exc)
            state.last_event = "Call request failed"
        state.record_activity(f"Twilio call failed: {exc}", "error")

def _cancel_call(state, call):
    with state.lock:
        if call["cancelled"]:
            return
        call["cancelled"] = True
        call["state"] = "cancelled"
        state.in_flight.pop(call["token"], None)
        call_uuid = call.get("call_uuid")
    if call_uuid:
        threading.Thread(target=state._hangup_call, args=(call_uuid,), daemon=True).start()

def start(state, priority_lead_id=None):
    priority = state._dialable_lead(priority_lead_id) if priority_lead_id else None
    with state.lock:
        if state.running:
            return state.public_state()
        state.activity_log.clear()
        state.activity_sequence = 0
    state.record_activity("Start dialing request received", "web")
    values = state._values()
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
    eligible = state._pool_leads()
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
        state._release_tokens()
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
        state._save_session()
        state.last_error = ""
        state.last_event = "Connecting computer audio"
        agent_call = state._new_call("agent", None)
        state.agent_call_token = agent_call["token"]
        state._schedule_calling_window_check()
    view = state.public_state()
    view["client_call_token"] = agent_call["token"]
    return view

def _new_call(state, kind, lead):
    token = secrets.token_urlsafe(24)
    call = {
        "token": token,
        "kind": kind,
        "lead_id": lead["id"] if lead else None,
        "lead": lead,
        "call_uuid": None,
        "state": "creating" if kind == "prospect" else "calling agent",
        "handled": False,
        "cancelled": False,
        "machine": False,
        "transcribing": False,
        "transcript_partials": {},
        "transcription_started": False,
        "caller_id": "",
        "answered_by": "",
        "picked_up": False,
        "connect_counted": False,
        "transcript_lines": [],
        "end_processed": False,
    }
    state.calls[token] = call
    state._watch_token(token)
    if kind == "prospect":
        state.in_flight[token] = call
        state._bump("dials")
        if state.session:
            state.session["dials"] += 1
            state._save_session()
    return call

def _watch_token(state, token):
    index = state.token_index
    if index is not None:
        index.register(token, state)

def _release_tokens(state):
    index = state.token_index
    if index is None:
        return
    for token in list(state.calls):
        index.forget(token)

def dial_lead(state, lead_id):
    lead = state._dialable_lead(lead_id)
    name = lead.get("name") or lead.get("phone") or "Prospect"
    with state.lock:
        running = state.running
    if not running:
        view = state.start(priority_lead_id=lead["id"])
        if view.get("client_call_token"):
            view["dial_status"] = "started"
            state.record_activity(f"Manual dial started for {name}", "web")
            return view
    return state._pin_manual_dial(lead, name)

def _dialable_lead(state, lead_id):
    lead_id = str(lead_id or "").strip()
    if not lead_id:
        raise ValueError("Choose a prospect to dial.")
    lead = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    if lead is None:
        raise KeyError("Prospect not found")
    if not str(lead.get("phone") or "").strip():
        raise ValueError("This prospect has no phone number.")
    if lead.get("status") == "do_not_call":
        raise ValueError("This prospect is marked do not call.")
    return lead

def _claim_manual_lead(state, leads, active_leads):
    lead_id = state.manual_lead_id
    if not lead_id:
        return None
    lead = next((item for item in leads if item["id"] == lead_id), None)
    blocked = (
        not lead
        or not lead.get("phone")
        or lead.get("status") == "do_not_call"
        or lead["id"] in active_leads
    )
    if blocked:
        state.manual_lead_id = None
        return None
    state.manual_lead_id = None
    return lead

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
        state.fill_slots()
    view = state.public_state()
    view["dial_status"] = status
    if status == "already":
        state.record_activity(f"Already dialing {name}", "web")
    else:
        state.record_activity(f"Manual dial {'placed' if status == 'now' else 'queued'} for {name}", "web")
    return view

def pause(state):
    with state.lock:
        if not state.running:
            return state.public_state()
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
        state.fill_slots()
    elif resume_countdown:
        state._schedule_advance(remaining)
    if should_check_hours:
        state._schedule_calling_window_check()
    return state.public_state()

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
            state._save_session()
    state.record_activity("Dialer stopped", "call")
    for call in calls:
        if call.get("call_uuid"):
            threading.Thread(target=state._hangup_call, args=(call["call_uuid"],), daemon=True).start()
    result = state.public_state()
    if summary:
        result["session_summary"] = summary
        if state.metrics:
            result["previous_session"] = next(
                (item for item in state.metrics.recent_sessions(5) if item.get("id") != summary["id"]),
                None,
                ) if hasattr(state.metrics, "recent_sessions") else None
    return result

