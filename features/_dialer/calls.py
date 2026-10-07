"""Caller rotation, call create/cancel, and the call dict. Below slots."""

import secrets
import threading

from features._dialer import session_stats, twilio_api

def _pool_leads(state, leads=None):
    leads = state.crm.snapshot() if leads is None else leads
    pool = [lead for lead in leads if lead["status"] == "new"]
    if state.selected_timezone:
        pool = [lead for lead in pool if (lead.get("timezone") or "Unknown") == state.selected_timezone]
    return pool

def _next_caller(state):
    with state.lock:
        if not state.callers:
            raise twilio_api.TwilioError("No voice-enabled Twilio numbers are available.")
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
    data = {
        "To": destination,
        "From": caller,
        "Url": twilio_api._url(state, call, "answer"),
        "Method": "GET",
        "StatusCallback": twilio_api._url(state, call, "status"),
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
            "AsyncAmdStatusCallback": twilio_api._url(state, call, "machine"),
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
            twilio_api._hangup_call(state, call_uuid)
        else:
            state.record_activity(f"Twilio call accepted for {lead_name}", "call")
    except twilio_api.TwilioError as exc:
        with state.lock:
            if call["kind"] == "agent":
                state.running = False
            else:
                state.in_flight.pop(call["token"], None)
                call["handled"] = True
                session_stats._bump(state, "failed")
            state.paused = True
            state.last_error = str(exc)
            state.last_event = "Call request failed"
        session_stats._flush_metrics(state)
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
        threading.Thread(target=twilio_api._hangup_call, args=(state, call_uuid), daemon=True).start()

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
    _watch_token(state, token)
    if kind == "prospect":
        state.in_flight[token] = call
        session_stats._bump(state, "dials")
        if state.session:
            state.session["dials"] += 1
            session_stats._save_session(state)
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
