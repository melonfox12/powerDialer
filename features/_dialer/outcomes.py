"""Disposition and prospect status changes during a call."""

from datetime import datetime, timezone

from features._dialer import queue, slots
from features._dialer import rules
from features._dialer.rules import record_disposition, status_for_disposition
from shared.vocabulary import (
    CALL_OUTCOME_KEYS,
    DEFAULT_OUTCOME_METRIC,
    OUTCOME_METRIC,
    STATUS_CALL_OUTCOME,
    STATUS_KEYS,
    canonical_status,
    parse_prospect_status,
)

def live_outcome_lead_id(state):
    """The lead id (if any) currently eligible for an outcome: either the call
    that is live on the line right now, or one that just ended and is waiting."""
    with state.lock:
        if state.pending_outcome:
            return state.pending_outcome
        if state.active:
            return state.active.get("lead_id")
        return None

def _on_a_call(state, lead_id):
    """True when this prospect is on a line, ringing, or waiting for an outcome after a call."""
    with state.lock:
        return (
            state.pending_outcome == lead_id
            or bool(state.active and state.active.get("lead_id") == lead_id)
            or any(call.get("kind") != "agent" and call.get("lead_id") == lead_id for call in state.in_flight.values())
        )


def end_call_with_status(state, lead_id, status, scheduled_until=None):
    """A status button: set the prospect's status, tag the call with it, and hang up.

    The status is stored on the prospect, so every view (Total dials, CRM, caller pool) reads the same one.
    """
    status = parse_prospect_status(status)
    if status not in STATUS_CALL_OUTCOME:
        raise ValueError("Choose a valid call status.")
    lead_id = str(lead_id or "").strip()
    previous = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    if previous is None:
        raise KeyError("Prospect not found")
    on_call = _on_a_call(state, lead_id)
    if status == "booked":
        lead = _set_booked(state, lead_id)
    elif status == "call":
        # A call on the line is already in the dial list, so it needs no separate skip entry.
        lead = queue.schedule_callback(state, lead_id, scheduled_until, log_skip=not on_call)
    else:
        lead = state.crm.set_status(lead_id, status)
    if on_call and status != "booked":
        _tag_recent_call(state, lead_id, STATUS_CALL_OUTCOME[status])
        if previous.get("status") != status:
            rules._bump(state, OUTCOME_METRIC.get(status, DEFAULT_OUTCOME_METRIC))
            rules._flush_metrics(state)
    with state.lock:
        if state.queue_anchor_id == lead_id:
            state.queue_anchor_id = None
    should_fill = queue.drop_prospect_call(state, lead_id)
    name = lead.get("name") or lead.get("business") or lead.get("phone") or "prospect"
    state.record_activity(f"{name} marked {status}", "web")
    with state.lock:
        state.last_event = f"{name} marked {status}"
    if should_fill:
        slots.fill_slots(state)
    return lead

def _set_booked(state, lead_id, scheduled_until=None):
    """Mark a prospect booked from the CRM and count the meeting once.

    choose_outcome counts its own bookings. A status change from the CRM must count too,
    or Performance never shows meetings that were booked outside a live call.
    """
    previous = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    lead = state.crm.set_status(lead_id, "booked", scheduled_until)
    _tag_recent_call(state, lead_id, "booked")
    if previous is not None and previous.get("status") == "booked":
        return lead
    rules._bump(state, OUTCOME_METRIC["booked"])
    with state.lock:
        if state.session:
            record_disposition(state.session, "booked")
            rules._save_session(state)
    rules._flush_metrics(state)
    return lead

def _tag_recent_call(state, lead_id, outcome):
    """Put the tag on the most recent connected call when it was with this prospect."""
    with state.lock:
        call = state.taggable_call
        if not call or call.get("lead_id") != lead_id:
            return False
        call["outcome"] = outcome
        call_ids = (call["token"], call.get("call_uuid"))
    try:
        state.crm.set_call_outcome(lead_id, call_ids, outcome)
    except (KeyError, ValueError, OSError) as exc:
        state.record_activity(f"Could not tag the call: {exc}", "error")
    return True

def tag_call(state, lead_id, outcome):
    """Tag the last connected call. Booked also marks the prospect booked and counts the meeting once."""
    if outcome not in CALL_OUTCOME_KEYS:
        raise ValueError("Choose a valid call outcome tag.")
    with state.lock:
        call = state.taggable_call
        if not call or call.get("lead_id") != lead_id:
            raise ValueError("There is no connected call to tag for that prospect.")
        if call.get("outcome") == "booked" and outcome != "booked":
            raise ValueError("A booked call stays booked.")
    if outcome == "booked":
        _set_booked(state, lead_id)
    else:
        _tag_recent_call(state, lead_id, outcome)
    return next(item for item in state.crm.snapshot() if item["id"] == lead_id)

def log_booking(state, lead_id, booked_at):
    """Count a meeting booked outside a live call, dated by the caller (ISO datetime with timezone).

    A prospect is counted once: one that already has a booking date is refused.
    """
    try:
        when = datetime.fromisoformat(str(booked_at))
    except ValueError as exc:
        raise ValueError("Booking date must be a valid ISO datetime.") from exc
    if when.tzinfo is None:
        raise ValueError("Booking date must include a timezone.")
    if when > datetime.now(timezone.utc):
        raise ValueError("A booking date cannot be in the future.")
    booked_at = when.astimezone(timezone.utc).isoformat()
    previous = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
    if previous is None:
        raise KeyError("Prospect not found")
    if previous.get("status") in ("disqualified", "no_answer_disqualified"):
        raise ValueError("A disqualified prospect cannot be marked booked.")
    if previous.get("booked_at"):
        raise ValueError("That booking already has a date and is counted.")
    if previous.get("status") == "booked":
        lead = state.crm.set_booked_at(lead_id, booked_at)
    else:
        _set_booked(state, lead_id)
        lead = state.crm.set_booked_at(lead_id, booked_at, replace_existing=True)
    state.record_activity(f"Booking logged for {lead.get('name') or lead.get('business') or 'prospect'}", "web")
    return lead

def update_status(state, lead_id, status=None, scheduled_until=None, disposition=None, crm_only=False):
    if disposition and not crm_only:
        status = status_for_disposition(disposition)
    raw = status
    status = parse_prospect_status(status)
    if status not in STATUS_KEYS:
        if raw is None or not str(raw).strip():
            previous = next((item for item in state.crm.snapshot() if item["id"] == lead_id), None)
            if previous is None:
                raise KeyError("Prospect not found")
            return previous
        raise ValueError(f"Unknown prospect status: {raw!r}")
    # Outcome buttons and CRM edits while someone is on a line end the call; otherwise just set status.
    if status in STATUS_CALL_OUTCOME and _on_a_call(state, lead_id):
        return end_call_with_status(state, lead_id, status, scheduled_until)
    if status == "booked":
        lead = _set_booked(state, lead_id, scheduled_until)
    else:
        lead = state.crm.set_status(lead_id, status, scheduled_until)
    if crm_only:
        with state.lock:
            state.queue_anchor_id = lead_id
        name = lead.get("name") or lead.get("business") or "prospect"
        state.record_activity(f"CRM status for {name} set to {status}", "web")
    return lead
