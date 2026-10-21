"""Caller rotation, call create/cancel, and the call dict. Below slots."""

import secrets
import threading

from features._dialer import rules, twilio
from shared.infra import utc_now

CALLER_IDS = (
    "+18607354163",
    "+18607521887",
    "+18607824999",
)

def _pool_leads(state, leads=None):
    leads = state.crm.snapshot() if leads is None else leads
    anchor_id = state.queue_anchor_id
    indexed = [
        (index, lead) for index, lead in enumerate(leads)
        if lead["status"] == "new"
    ]
    if state.selected_timezone:
        zone = state.selected_timezone
        indexed = [
            (index, lead) for index, lead in indexed
            if lead["id"] == anchor_id or (lead.get("timezone") or "Unknown") == zone
        ]
    indexed.sort(key=lambda item: (bool(item[1].get("passed_at")), item[1].get("passed_at") or "", item[0]))
    ordered = [lead for _index, lead in indexed]
    if anchor_id:
        held = [lead for lead in ordered if lead["id"] == anchor_id]
        rest = [lead for lead in ordered if lead["id"] != anchor_id]
        ordered = held + rest
    return ordered

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
