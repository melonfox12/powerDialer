"""Disposition and prospect status changes during a call."""

from features._dialer import timing
from features._dialer import session_stats
from features._dialer.session_stats import record_disposition, status_for_disposition
from shared.vocabulary import DEFAULT_OUTCOME_METRIC, OUTCOME_METRIC

def live_outcome_lead_id(state):
    """The lead id (if any) currently eligible for an outcome: either the call
    that is live on the line right now, or one that just ended and is waiting."""
    with state.lock:
        if state.pending_outcome:
            return state.pending_outcome
        if state.active:
            return state.active.get("lead_id")
        return None

def choose_outcome(state, lead_id, status, scheduled_until=None):
    if status not in ("call", "disqualified", "booked", "interested", "do_not_call"):
        raise ValueError("Choose a valid call outcome.")
    with state.lock:
        live_call = state.active if state.active and state.active.get("lead_id") == lead_id else None
        if state.pending_outcome != lead_id and not live_call:
            raise ValueError("That prospect is not waiting for an outcome.")
        if live_call:
            live_call["outcome_chosen"] = True
    result = state.crm.set_status(lead_id, status, scheduled_until)
    metric_key = OUTCOME_METRIC.get(status, DEFAULT_OUTCOME_METRIC)
    session_stats._bump(state, metric_key)
    session_stats._flush_metrics(state)
    with state.lock:
        if state.session:
            record_disposition(state.session, status)
            session_stats._save_session(state)
        if state.pending_outcome == lead_id:
            state.pending_outcome = None
        state.last_event = f"{result['name'] or result['phone']} marked {status}"
        can_continue = state.running and not state.paused and not live_call
    session_stats._flush_metrics(state)
    if can_continue:
        timing._schedule_advance(state)
    return result

def update_status(state, lead_id, status=None, scheduled_until=None, disposition=None):
    if disposition:
        status = status_for_disposition(disposition)
    with state.lock:
        is_outcome = live_outcome_lead_id(state) == lead_id and status in (
            "call", "disqualified", "booked", "interested", "do_not_call"
        )
    if is_outcome:
        return choose_outcome(state, lead_id, status, scheduled_until)
    return state.crm.set_status(lead_id, status, scheduled_until)
