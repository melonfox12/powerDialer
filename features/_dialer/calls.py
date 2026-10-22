"""Caller rotation, call create/cancel, and the call dict. Below slots."""

import secrets
import threading
from datetime import datetime, timedelta, timezone

from features._dialer import rules, twilio
from features._prospects.csv_import import location_text
from shared.infra import utc_now

CALLER_IDS = (
    "+18607354163",
    "+18607521887",
    "+18607824999",
)
RECENT_DIAL_WINDOW = timedelta(hours=12)
# answered_by labels written by drops we make ourselves.
RACE_LOST = "race_lost"
CANCELLED = "cancelled"
UNCLEAR = "unclear"
# How long a lead stays out of the queue after a dial that did not reach a person.
# Any other label (connected, skipped, unlabelled) uses RECENT_DIAL_WINDOW.
RETRY_AFTER = {
    "no_answer": timedelta(hours=3),
    "voicemail": timedelta(hours=4),
    UNCLEAR: timedelta(hours=4),
    RACE_LOST: timedelta(minutes=2),
    CANCELLED: timedelta(minutes=2),
}
CALLBACK_HOLD = timedelta(hours=12, seconds=2)

def _dial_times(lead):
    """Times shown on Total dials: each call record, or the transcript when that is all we have."""
    log = lead.get("call_log") or []
    if log:
        return [item.get("started_at") or item.get("ended_at") or "" for item in log]
    return [line.get("timestamp") or "" for line in (lead.get("transcript") or [])]

def _folded(value):
    return " ".join(str(value or "").split()).casefold()


def _identity(lead):
    """Name plus location. City and state are the location; timezone is used when both are blank."""
    name = _folded(lead.get("name"))
    if not name:
        return None
    city = _folded(location_text(lead, "city"))
    state_name = _folded(location_text(lead, "state"))
    if city or state_name:
        place = (city, state_name)
    else:
        place = ("", _folded(lead.get("timezone")))
    return (name, place)


def _callback_due(lead):
    try:
        moment = datetime.fromisoformat(str(lead.get("scheduled_until") or ""))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def callback_sync_plan(leads, now):
    """New prospects that match a Total dials prospect still inside a 12-hour callback.

    The copy keeps that prospect's callback time, so a delete-and-reimport does not
    put someone back in the queue while the original callback is still running.
    """
    sources = {}
    for lead in leads or []:
        if lead.get("status") != "call" or not _dial_times(lead):
            continue
        due = _callback_due(lead)
        if due is None:
            continue
        remaining = due - now
        if remaining <= timedelta(0) or remaining > CALLBACK_HOLD:
            continue
        key = _identity(lead)
        if key is None:
            continue
        current = sources.get(key)
        if current is None or due > current[0]:
            sources[key] = (due, due.isoformat(), lead.get("id"))
    copies = []
    for lead in leads or []:
        if lead.get("status") != "new":
            continue
        key = _identity(lead)
        source = sources.get(key)
        if source is None or lead.get("id") == source[2]:
            continue
        copies.append({"id": lead["id"], "scheduled_until": source[1]})
    return copies


def _dial_windows(lead):
    """(time, wait) for each dial: the wait depends on how that dial ended."""
    log = lead.get("call_log") or []
    if log:
        return [
            (item.get("started_at") or item.get("ended_at") or "",
             RETRY_AFTER.get(item.get("answered_by"), RECENT_DIAL_WINDOW))
            for item in log
        ]
    return [(raw, RECENT_DIAL_WINDOW) for raw in _dial_times(lead)]


def _dialed_recently(lead, now=None):
    moment_now = now or utc_now()
    for raw, wait in _dial_windows(lead):
        try:
            moment = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        if moment > moment_now - wait:
            return True
    return False

def _pool_leads(state, leads=None):
    leads = state.crm.snapshot() if leads is None else leads
    anchor_id = state.queue_anchor_id
    indexed = [
        (index, lead) for index, lead in enumerate(leads)
        if lead["status"] == "new" and not _dialed_recently(lead)
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
        "line_seen_at": None,
        "answered_at": None,
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
