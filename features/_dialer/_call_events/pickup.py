"""Pickup and answer detection."""

from datetime import datetime, timezone

from features._dialer import calls
from features._dialer import rules
from features._dialer import twilio
from features._dialer.rules import add_connect

def _drop_to_callback(state, call):
    """Hang up a line that lost the race and schedule a callback."""
    with state.lock:
        if call.get("picked_up") or call.get("skip_closed"):
            return
        call["skip_closed"] = True
        lead_id = call.get("lead_id")
        name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
    calls._cancel_call(state, call)
    if not lead_id:
        return
    from features._dialer.queue import _schedule_callback
    try:
        _schedule_callback(state, lead_id)
    except (KeyError, ValueError, OSError) as exc:
        state.record_activity(f"Could not set a callback for {name}: {exc}", "error")
        return
    state.record_activity(f"Dropped {name}; callback set", "call")
    from features._dialer import timing
    timing._schedule_advance(state)


def _pickup(state, call):
    """Connect the first answer into the conference and callback the other lines."""
    with state.lock:
        if call["kind"] != "prospect" or call["cancelled"] or not state.running:
            return False
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
            if state.session and not call.get("connect_counted"):
                add_connect(state.session)
                call["connect_counted"] = True
                rules._save_session(state)
            name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
            caller = call.get("caller_id") or ""
            state.last_event = f"Picked up {name}" + (f" from {caller}" if caller else "")
            others = [item for item in state.in_flight.values() if item is not call]
    if lost:
        _drop_to_callback(state, call)
        return False
    rules._flush_metrics(state)
    for other in others:
        _drop_to_callback(state, other)
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
        name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
        if label == "voicemail":
            state.last_event = f"Voicemail on the line: {name}"
        elif label == "human":
            state.last_event = f"Live voice: {name}"
        else:
            state.last_event = f"On the line: {name}"
    rules._flush_metrics(state)
    if label == "human":
        if not call.get("picked_up") and _pickup(state, call):
            twilio._redirect_call(state, call.get("call_uuid"), twilio._url(state, call, "answer"))
    elif not call.get("picked_up"):
        _drop_to_callback(state, call)
    kept = label == "human" and call.get("picked_up") and state.active is call
    state.record_activity(
        "Live voice is on the line" if kept
        else "Voicemail hung up" if label == "voicemail"
        else "Answer was not a person",
        "call",
    )
    return 200, "text/plain", "OK"
