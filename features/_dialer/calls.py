"""Caller rotation, call create/cancel, and the call dict. Below slots."""

import secrets
import threading
from datetime import datetime, timedelta, timezone

from features._dialer import rules, twilio
from shared.dial_policy import (
    CALLBACK_HOLD,
    CANCELLED,
    DEAD_LINE,
    MANUAL_CALLBACK,
    NO_PICKUP_CALLBACK,
    RACE_LOST,
    RECENT_DIAL_WINDOW,
    RETRY_AFTER,
    callback_due,
    callback_sync_plan,
    contact_keys,
    dialed_recently,
    is_never_dial_status,
    manual_lead_blocked,
    pool_leads,
    resolve_pool_status,
)
from shared.infra import utc_now
CALLER_IDS = (
    "+18607354163",
    "+18607521887",
    "+18607824999",
)

def _callback_due(lead):
    return callback_due(lead)


def _dialed_recently(lead, now=None):
    return dialed_recently(lead, now)


def _contact_keys(lead):
    return contact_keys(lead)


def _busy_lead_ids(state):
    """Leads on a line, ringing, or waiting for an outcome right now."""
    with state.lock:
        busy = {call["lead_id"] for call in state.in_flight.values() if call.get("lead_id")}
        if state.active and state.active.get("lead_id"):
            busy.add(state.active["lead_id"])
        if state.pending_outcome:
            busy.add(state.pending_outcome)
    return busy


def _pool_leads(state, leads=None):
    leads = state.crm.snapshot() if leads is None else leads
    return pool_leads(
        leads,
        pool_status=resolve_pool_status(getattr(state, "dial_pool_status", None)),
        busy_ids=_busy_lead_ids(state),
        now=utc_now(),
        selected_timezone=state.selected_timezone,
        anchor_id=state.queue_anchor_id,
    )

def _next_caller(state):
    with state.lock:
        if not state.callers:
            raise twilio.TwilioError("No voice-enabled Twilio numbers are available.")
        caller = state.callers[state.caller_index % len(state.callers)]
        state.caller_index += 1
        return caller

def _launch_call(state, call, destination):
    if not call.get("caller_id"):
        call["caller_id"] = _next_caller(state)
    threading.Thread(target=_create_call, args=(state, call, destination), daemon=True).start()

def _create_call(state, call, destination):
    caller = call.get("caller_id") or _next_caller(state)
    call["caller_id"] = caller
    number = twilio.normalize_phone(destination) or str(destination or "").strip()
    data = {
        "To": number,
        "From": caller,
        "Url": twilio._url(state, call, "answer"),
        "Method": "GET",
        "StatusCallback": twilio._url(state, call, "status"),
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
            "MachineDetectionSpeechThreshold": "4000",
            "MachineDetectionSpeechEndThreshold": "1200",
            "AsyncAmdStatusCallback": twilio._url(state, call, "machine"),
            "AsyncAmdStatusCallbackMethod": "POST",
        })
    lead_name = (call.get("lead") or {}).get("name") or "prospect"
    state.record_activity(f"Requesting Twilio call for {lead_name}", "api")
    try:
        result = twilio.twilio_request(state.settings["TWILIO_ACCOUNT_SID"], state.settings["TWILIO_AUTH_TOKEN"],
                                "POST", "/Calls.json", data=data)
        call_uuid = result.get("sid")
        if not call_uuid:
            raise twilio.TwilioError("Twilio did not return a call SID.")
        with state.lock:
            call["call_uuid"] = call_uuid
            if call["kind"] == "agent":
                state.agent_call_uuid = call_uuid
            cancelled = call["cancelled"]
            if not cancelled:
                state.last_event = "Ringing agent" if call["kind"] == "agent" else "Calling prospects"
        if cancelled:
            twilio._hangup_call(state, call_uuid)
        else:
            state.record_activity(f"Twilio call accepted for {lead_name}", "call")
            if call["kind"] == "prospect":
                timer = threading.Timer(30, _expire_silent_call, args=(state, call["token"]))
                timer.daemon = True
                timer.start()
    except twilio.TwilioError as exc:
        account_rejected = "Twilio error 401" in str(exc)
        refill = False
        lead_id = call.get("lead_id")
        siblings = []
        with state.lock:
            if call["kind"] == "agent" or account_rejected:
                if call["kind"] == "agent":
                    state.running = False
                else:
                    state.in_flight.pop(call["token"], None)
                    call["handled"] = True
                    call["cancelled"] = True
                    rules._bump(state, "failed")
                    siblings = [item["token"] for item in state.in_flight.values()]
                state.paused = True
                state.last_error = str(exc)
                state.last_event = "Call request failed"
            else:
                state.in_flight.pop(call["token"], None)
                call["handled"] = True
                call["cancelled"] = True
                rules._bump(state, "failed")
                state.last_event = "Call request failed"
                refill = True
        rules._flush_metrics(state)
        state.record_activity(f"Twilio call failed: {exc}", "error")
        for token in siblings:
            other = state.calls.get(token)
            if other:
                _cancel_call(state, other)
        if refill:
            _replace_line_after_delay(state, lead_id)

def _expire_silent_call(state, token):
    """Drop a line Twilio stopped reporting, so the queue does not sit on it."""
    with state.lock:
        call = state.calls.get(token)
        if (
            not call
            or call.get("end_processed")
            or call.get("picked_up")
            or call.get("cancelled")
            or call.get("skip_closed")
            or state.active is call
            or call["token"] not in state.in_flight
        ):
            return
        call_uuid = call.get("call_uuid")
    if call_uuid:
        twilio._hangup_call(state, call_uuid)
    from features._dialer._call_events import ended
    ended._call_ended(state, call, {"CallStatus": "no-answer", "CallDuration": "0"})

def _replace_line_after_delay(state, lead_id):
    """Move a failed prospect back and wait before filling that open line."""
    if lead_id:
        try:
            state.crm.defer(lead_id)
        except (KeyError, ValueError, OSError):
            pass
    from features._dialer import timing
    timing._schedule_advance(state)

def _cancel_call(state, call):
    with state.lock:
        if call["cancelled"]:
            return
        call["cancelled"] = True
        call["state"] = "cancelled"
        state.in_flight.pop(call["token"], None)
        call_uuid = call.get("call_uuid")
    if call_uuid:
        threading.Thread(target=twilio._hangup_call, args=(state, call_uuid), daemon=True).start()

def _dial_record(call, duration, answered_by=None):
    """The one call-log entry for a finished dial. It replaces the entry written at dial time."""
    answered = answered_by or call.get("answered_by") or ""
    if not answered:
        answered = "unknown" if call.get("picked_up") else "no_answer"
    return {
        "id": call.get("call_uuid") or call["token"],
        "started_at": call.get("created_at") or call.get("connected_at") or "",
        "ended_at": datetime.now(timezone.utc).isoformat(),
        "caller_id": call.get("caller_id") or "",
        "answered_by": answered,
        "duration_seconds": duration,
        "transcript_lines": len(call.get("transcript_lines") or []),
        # Connected means the agent was on the line with the prospect, not voicemail or a dead line.
        "connected": bool(call.get("picked_up")) and str(answered) != "voicemail",
        "outcome": call.get("outcome"),
    }

def _new_call(state, kind, lead):
    token = secrets.token_urlsafe(24)
    call = {
        "token": token,
        "kind": kind,
        "lead_id": lead["id"] if lead else None,
        "lead": lead,
        "call_uuid": None,
        "created_at": utc_now().isoformat(),
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
    _watch_token(state, token)
    if kind == "prospect":
        state.in_flight[token] = call
        rules._bump(state, "dials")
        if state.session:
            state.session["dials"] += 1
            rules._save_session(state)
        if lead and lead.get("id"):
            try:
                state.crm.append_call_log(lead["id"], {
                    "id": token,
                    "started_at": call["created_at"],
                    "ended_at": "",
                    "caller_id": "",
                    "answered_by": "",
                    "duration_seconds": 0,
                    "transcript_lines": 0,
                })
            except (KeyError, ValueError, OSError):
                pass
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

def _dialable_lead(state, lead_id):
    lead_id = str(lead_id or "").strip()
    if not lead_id:
        raise ValueError("Choose a prospect to dial.")
    lead = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    if lead is None:
        raise KeyError("Prospect not found")
    if not str(lead.get("phone") or "").strip():
        raise ValueError("This prospect has no phone number.")
    if is_never_dial_status(lead.get("status")):
        raise ValueError("This prospect is already closed and is never dialed again.")
    return lead

def _claim_manual_lead(state, leads, active_leads):
    """The pinned prospect, unless they are closed, already on a line, or the same person as someone who is."""
    lead_id = state.manual_lead_id
    if not lead_id:
        return None
    lead = next((item for item in leads if item["id"] == lead_id), None)
    blocked = manual_lead_blocked(lead, leads, active_leads)
    if blocked:
        state.manual_lead_id = None
        return None
    state.manual_lead_id = None
    return lead
