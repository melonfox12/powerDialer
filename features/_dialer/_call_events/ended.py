"""Prospect and agent call endings."""

from datetime import datetime, timezone

from features._dialer import calls, timing
from features._dialer import rules
from features._dialer.rules import record_conversation

def _dial_record(call, duration):
    answered = call.get("answered_by") or ""
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

def _call_ended(state, call, params):
    log_entry = None
    should_schedule_advance = False
    others = []
    with state.lock:
        if call["kind"] == "agent":
            _agent_call_ended(state)
            return
        if state.queue_anchor_id == call.get("lead_id"):
            state.queue_anchor_id = None
        if call.get("end_processed"):
            return
        call["end_processed"] = True
        if call["cancelled"] and not call.get("picked_up"):
            state.in_flight.pop(call["token"], None)
            if state.active is call:
                state.active = None
            if call.get("call_uuid"):
                log_entry = _dial_record(call, 0)
        else:
            was_connected = bool(call.get("picked_up")) or state.active is call
            call["handled"] = True
            call["state"] = "ended"
            state.in_flight.pop(call["token"], None)
            if state.active is call:
                state.active = None
            outcome_already_chosen = call.get("outcome_chosen")
            pending_already = state.pending_outcome == call.get("lead_id")
            duration = 0
            if was_connected:
                try:
                    duration = int(float(params.get("CallDuration") or params.get("Duration") or params.get("BillDuration") or 0))
                except (TypeError, ValueError):
                    duration = 0
                rules._bump(state, "connected")
                if duration:
                    rules._bump(state, "talk_seconds", duration)
                    threshold = int(state.settings.get("CONVERSATION_THRESHOLD_SECONDS", "30"))
                    if state.session and call.get("answered_by") != "voicemail":
                        record_conversation(state.session, duration, threshold)
                rules._save_session(state)
            log_entry = _dial_record(call, duration)
            if state.running and was_connected:
                if outcome_already_chosen:
                    state.last_event = "Call ended"
                    should_schedule_advance = not pending_already and not state.pending_outcome
                elif not pending_already:
                    state.pending_outcome = call["lead_id"]
                    state.last_event = "Choose an outcome before the next calls"
            elif state.running and not was_connected and not pending_already and not outcome_already_chosen:
                state.last_event = "No answer"
                should_schedule_advance = True
            others = list(state.in_flight.values()) if state.running else []
    rules._flush_metrics(state)
    for other in others:
        calls._cancel_call(state, other)
    if log_entry and call.get("lead_id"):
        try:
            state.crm.append_call_log(call["lead_id"], log_entry)
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not log the call: {exc}", "error")
    if should_schedule_advance:
        timing._schedule_advance(state)

def _agent_call_ended(state):
    with state.lock:
        state.agent_ready = False
        if state.running and not state.pending_outcome:
            state.paused = True
            state.last_event = "Computer audio disconnected; dialer paused"
