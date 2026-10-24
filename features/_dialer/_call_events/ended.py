"""Prospect and agent call endings."""

from features._dialer import calls, queue, timing
from features._dialer import rules
from features._dialer.rules import record_conversation
from shared.vocabulary import CONVERSATION_MIN_SECONDS, NEVER_DIAL_STATUSES

def _call_ended(state, call, params):
    log_entry = None
    should_schedule_advance = False
    should_refill = False
    others = []
    with state.lock:
        if call["kind"] == "agent":
            _agent_call_ended(state)
            return
        if state.queue_anchor_id == call.get("lead_id"):
            state.queue_anchor_id = None
        if call.get("end_processed"):
            return
        if call.get("skip_closed"):
            call["end_processed"] = True
            state.in_flight.pop(call["token"], None)
            if state.active is call:
                state.active = None
            if state.pending_outcome == call.get("lead_id"):
                state.pending_outcome = None
            return
        call["end_processed"] = True
        if call["cancelled"] and not call.get("picked_up"):
            state.in_flight.pop(call["token"], None)
            if state.active is call:
                state.active = None
            if call.get("call_uuid"):
                log_entry = calls._dial_record(call, 0, calls.CANCELLED)
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
                    threshold = int(state.settings.get("CONVERSATION_THRESHOLD_SECONDS", CONVERSATION_MIN_SECONDS))
                    if state.session and call.get("picked_up") and call.get("answered_by") != "voicemail":
                        record_conversation(state.session, duration, threshold)
                rules._save_session(state)
            log_entry = calls._dial_record(call, duration)
            if state.running and was_connected:
                state.last_event = "Call ended"
                should_schedule_advance = not pending_already and not state.pending_outcome
                others = list(state.in_flight.values())
            elif state.running and not was_connected and not pending_already and not outcome_already_chosen:
                state.last_event = "No answer"
                should_refill = not state.active and not state.pending_outcome and not state.paused
                others = []
            else:
                others = []
    rules._flush_metrics(state)
    for other in others:
        calls._cancel_call(state, other)
    if log_entry and call.get("lead_id"):
        try:
            state.crm.append_call_log(call["lead_id"], log_entry, call.get("token"))
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not log the call: {exc}", "error")
    if should_schedule_advance:
        timing._schedule_advance(state)
    elif should_refill:
        lead_id = call.get("lead_id")
        if lead_id:
            try:
                lead = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
                if lead and lead.get("status") not in NEVER_DIAL_STATUSES:
                    queue.schedule_no_pickup_callback(state, lead_id)
            except (KeyError, ValueError, OSError) as exc:
                state.record_activity(f"Could not schedule callback for unanswered prospect: {exc}", "error")
        timing._schedule_advance(state)

def _agent_call_ended(state):
    with state.lock:
        state.agent_ready = False
        if state.running and not state.pending_outcome:
            state.paused = True
            state.last_event = "Computer audio disconnected; dialer paused"
