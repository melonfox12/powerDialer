"""Pickup and answer detection."""

from datetime import datetime, timezone

from features._dialer import calls
from features._dialer import queue
from features._dialer import rules
from features._dialer import timing
from features._dialer import twilio
from features._dialer.rules import add_connect

def _name(call):
    lead = call.get("lead") or {}
    return lead.get("name") or lead.get("phone") or "prospect"

def _drop_line(state, call, answered_by):
    """Hang up a line that will not reach the agent and log it once.

    No-pickup drops schedule a 48-hour CRM callback when the prospect is still New.
    """
    with state.lock:
        if call.get("picked_up") or call.get("skip_closed"):
            return False
        call["skip_closed"] = True
    calls._cancel_call(state, call)
    lead_id = call.get("lead_id")
    if lead_id:
        try:
            state.crm.append_call_log(lead_id, calls._dial_record(call, 0, answered_by), call["token"])
            queue.maybe_enforce_dial_caps(state)
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not log the call for {_name(call)}: {exc}", "error")
    if lead_id and answered_by in ("voicemail", calls.RACE_LOST, calls.DEAD_LINE, calls.CANCELLED):
        try:
            queue.schedule_no_pickup_callback(state, lead_id)
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not set the callback for {_name(call)}: {exc}", "error")
    label = answered_by.replace("_", " ")
    state.record_activity(f"Dropped {_name(call)} ({label}); 48-hour callback when eligible", "call")
    timing._schedule_advance(state)
    return True

def _pickup(state, call):
    """Connect the first answer into the conference and drop the other lines."""
    with state.lock:
        if call["kind"] != "prospect" or call["cancelled"] or not state.running:
            return False
        rules.clear_stale_active(state)
        if call.get("picked_up"):
            return state.active is call
        if state.active and state.active is not call:
            lost = True
            others = []
        else:
            lost = False
            call["picked_up"] = True
            call["state"] = "live"
            call["connected_at"] = datetime.now(timezone.utc).isoformat()
            state.active = call
            state.taggable_call = call
            if state.session and not call.get("connect_counted"):
                add_connect(state.session)
                call["connect_counted"] = True
                rules._save_session(state)
            name = _name(call)
            caller = call.get("caller_id") or ""
            state.last_event = f"Picked up {name}" + (f" from {caller}" if caller else "")
            others = [item for item in state.in_flight.values() if item is not call]
    if lost:
        _drop_line(state, call, calls.RACE_LOST)
        return False
    rules._flush_metrics(state)
    for other in others:
        _drop_line(state, other, calls.RACE_LOST)
    state.record_activity(f"Pickup on the line: {name}. Stay on it or skip.", "call")
    return True

def _machine_result(state, call, params):
    answered_by = str(params.get("AnsweredBy") or params.get("MachineDetectionResult") or "unknown").lower()
    state.record_activity(f"Answer detection: {answered_by}", "call")
    result = " ".join(str(params.get(key, "")) for key in (
        "AnsweredBy", "Machine", "machine", "MachineDetection", "MachineDetectionResult", "machine_detection"
    )).lower()
    machine = any(term in result for term in ("machine", "voicemail", "fax", "answering service"))
    human = "human" in result and not machine
    # Twilio could not decide. Connect: a person who answers instantly (a front desk) is real.
    label = "voicemail" if machine else "human" if human else "unknown"
    with state.lock:
        if call["cancelled"] or call.get("end_processed"):
            return 200, "text/plain", "OK"
        call["answered_by"] = label
        if machine:
            call["machine"] = True
            if not call.get("machine_counted"):
                call["machine_counted"] = True
                rules._bump(state, "voicemail")
        name = _name(call)
        if label == "voicemail":
            state.last_event = f"Voicemail on the line: {name}"
        elif label == "human":
            state.last_event = f"Live voice: {name}"
        else:
            state.last_event = f"On the line: {name}"
    rules._flush_metrics(state)
    if machine:
        if not call.get("picked_up"):
            _drop_line(state, call, "voicemail")
        message = "Voicemail hung up"
    elif label == "unknown" and not call.get("picked_up") and not twilio._call_is_live(state, call.get("call_uuid")):
        # Twilio reports "unknown" for lines that already hung up. Do not put the agent on a dead line.
        _drop_line(state, call, calls.DEAD_LINE)
        message = "Line was already gone"
    else:
        if not call.get("picked_up") and _pickup(state, call):
            twilio._redirect_call(state, call.get("call_uuid"), twilio._url(state, call, "answer"))
        kept = call.get("picked_up") and state.active is call
        if kept:
            message = "Live voice is on the line" if human else "Answer unclear; connected you"
        else:
            message = "Another line was already live"
    state.record_activity(message, "call")
    return 200, "text/plain", "OK"
