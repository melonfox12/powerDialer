"""Prospect and agent call endings."""

from features._dialer import calls, queue, slots, timing
from features._dialer import rules
from features._dialer import live_transcript
from shared.vocabulary import TRANSCRIPT_SOURCE_TWILIO
from features._dialer.rules import record_conversation


def _call_ended(state, call, params):
    log_entry = None
    should_schedule_advance = False
    should_top_up = False
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
        if call.get("lead_id"):
            live_transcript.commit_partials(state, call, source=TRANSCRIPT_SOURCE_TWILIO)
        pending_already = state.pending_outcome == call.get("lead_id")
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
            rules.clear_stale_active(state)
            outcome_already_chosen = call.get("outcome_chosen")
            prospect_hung_up = was_connected and not pending_already and not call.get("wrapping")
            duration = 0
            if was_connected:
                try:
                    duration = int(float(params.get("CallDuration") or params.get("Duration") or params.get("BillDuration") or 0))
                except (TypeError, ValueError):
                    duration = 0
                rules._bump(state, "connected")
                if duration:
                    rules._bump(state, "talk_seconds", duration)
                if (
                    state.session
                    and call.get("picked_up")
                    and call.get("answered_by") != "voicemail"
                    and len(call.get("transcript_lines") or []) > 0
                ):
                    record_conversation(state.session)
                rules._save_session(state)
            log_entry = calls._dial_record(call, duration)
            if state.running and was_connected:
                state.last_event = (
                    "Prospect hung up" if prospect_hung_up else "Call ended"
                )
                should_schedule_advance = (
                    prospect_hung_up or (not pending_already and not state.pending_outcome)
                )
                others = list(state.in_flight.values())
            elif not was_connected and not pending_already and not outcome_already_chosen:
                if state.running:
                    state.last_event = "No answer"
                should_top_up = (
                    state.running
                    and not state.active
                    and not state.pending_outcome
                    and not state.paused
                )
                others = []
            else:
                others = []
    rules._flush_metrics(state)
    for other in others:
        calls._cancel_call(state, other)
    if log_entry and call.get("lead_id"):
        try:
            state.crm.append_call_log(call["lead_id"], log_entry, call.get("token"))
            if getattr(state, "ai_agent_mode", False):
                from features import ai_agents
                was_live = bool(call.get("picked_up")) and call.get("answered_by") != "voicemail"
                ai_agents.finalize_agent_call(
                    state,
                    call["lead_id"],
                    connected=was_live,
                    voicemail=call.get("answered_by") == "voicemail",
                )
                with state.lock:
                    if state.pending_outcome == call.get("lead_id"):
                        state.pending_outcome = None
                ai_agents.try_resume_agent_dial(state)
            queue.maybe_enforce_dial_caps(state)
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not log the call: {exc}", "error")
    if should_schedule_advance:
        timing._schedule_advance(state)
    elif should_top_up:
        slots.request_top_up(state)


def _agent_call_ended(state):
    with state.lock:
        state.agent_ready = False
        if state.running and not state.pending_outcome:
            state.last_event = "Computer audio disconnected; reconnecting…"
