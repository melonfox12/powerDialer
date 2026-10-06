"""Pickup and answer detection."""

from datetime import datetime, timezone

from features._dialer.session_stats import add_connect

def _pickup(state, call):
    """Bridge any answer, including voicemail, so the rep can hear it."""
    with state.lock:
        if call["kind"] != "prospect" or call["cancelled"] or not state.running:
            return False
        if call.get("picked_up"):
            return False
        call["picked_up"] = True
        call["state"] = "live"
        call["connected_at"] = datetime.now(timezone.utc).isoformat()
        state.active = call
        if state.session and not call.get("connect_counted"):
            add_connect(state.session)
            call["connect_counted"] = True
            state._save_session()
        name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
        caller = call.get("caller_id") or ""
        state.last_event = f"Picked up {name}" + (f" from {caller}" if caller else "")
        others = [item for item in state.in_flight.values() if item is not call]
    for other in others:
        state._cancel_call(other)
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
                state._bump("voicemail")
        name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
        if label == "voicemail":
            state.last_event = f"Voicemail on the line: {name}"
        elif label == "human":
            state.last_event = f"Live voice: {name}"
        else:
            state.last_event = f"On the line: {name}"
    if not call.get("picked_up"):
        state._pickup(call)
    state.record_activity(
        "Voicemail is on the line" if label == "voicemail"
        else "Live voice is on the line" if label == "human"
        else "Pickup is on the line",
        "call",
    )
    return 200, "text/plain", "OK"
