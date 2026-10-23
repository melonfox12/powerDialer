"""Disposition and prospect status changes during a call."""

from features._dialer import queue, timing
from features._dialer import rules
from features._dialer.rules import record_disposition, status_for_disposition
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
    rules._bump(state, metric_key)
    rules._flush_metrics(state)
    with state.lock:
        if state.session:
            record_disposition(state.session, status)
            rules._save_session(state)
        if state.pending_outcome == lead_id:
            state.pending_outcome = None
        state.last_event = f"{result['name'] or result['phone']} marked {status}"
        can_continue = state.running and not state.paused and not live_call
    rules._flush_metrics(state)
    if can_continue:
        timing._schedule_advance(state)
    return result

def _set_booked(state, lead_id, scheduled_until=None):
    """Mark a prospect booked from the CRM and count the meeting once.

    choose_outcome counts its own bookings. A status change from the CRM must count too,
    or Performance never shows meetings that were booked outside a live call.
    """
    previous = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    lead = state.crm.set_status(lead_id, "booked", scheduled_until)
    if previous is not None and previous.get("status") == "booked":
        return lead
    rules._bump(state, OUTCOME_METRIC["booked"])
    with state.lock:
        if state.session:
            record_disposition(state.session, "booked")
            rules._save_session(state)
    rules._flush_metrics(state)
    return lead

def update_status(state, lead_id, status=None, scheduled_until=None, disposition=None, crm_only=False):
    if disposition and not crm_only:
        status = status_for_disposition(disposition)
    if crm_only and status == "booked":
        lead = _set_booked(state, lead_id, scheduled_until)
        name = lead.get("name") or lead.get("business") or "prospect"
        state.record_activity(f"CRM status for {name} set to booked", "web")
        return lead
    if crm_only and status == "call":
        return queue.callback_skip(state, lead_id)
    if crm_only and status == "disqualified":
        return queue.disqualify_prospect(state, lead_id)
    if not crm_only:
        with state.lock:
            is_outcome = live_outcome_lead_id(state) == lead_id and status in (
                "call", "disqualified", "booked", "interested", "do_not_call"
            )
        if is_outcome:
            return choose_outcome(state, lead_id, status, scheduled_until)
        if status == "booked":
            return _set_booked(state, lead_id, scheduled_until)
        return state.crm.set_status(lead_id, status, scheduled_until)
    lead = state.crm.set_status(lead_id, status, scheduled_until)
    with state.lock:
        state.queue_anchor_id = lead_id
    name = lead.get("name") or lead.get("business") or "prospect"
    state.record_activity(f"CRM status for {name} set to {status}", "web")
    return lead
