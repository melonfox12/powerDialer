"""Public and live snapshots."""

from features._dialer import calls
from features._dialer.rules import clear_stale_active, dialer_stage, new_session, recent_streak
from shared.dial_policy import leads_for_timezone_counts, resolve_pool_status, unique_business_types
from shared.vocabulary import resolve_caller_id_group
from shared.infra import utc_now

def crm_catalog(state, leads=None):
    """Lead rows plus derived pool, timezone counts, and summary counts."""
    leads = leads if leads is not None else state.crm.snapshot()
    pool_status = resolve_pool_status(getattr(state, "dial_pool_status", None))
    business_type = getattr(state, "selected_business_type", None) or None
    groups = state.crm.timezone_groups(
        leads_for_timezone_counts(leads, pool_status, utc_now(), selected_business_type=business_type),
    )
    pool = calls._pool_leads(state, leads)
    return {
        "leads_version": getattr(state.crm, "revision", 0),
        "leads": leads,
        "pool": pool,
        "timezone_groups": [{"name": name, "count": count} for name, count in groups],
        "business_type_options": unique_business_types(leads),
        "counts": {
            "total": len(leads),
            "new": sum(lead["status"] == "new" for lead in leads),
            "calling": 0,
            "booked": sum(lead["status"] == "booked" for lead in leads),
        },
    }


def leads_catalog(state):
    """Full CRM table payload for GET /api/leads."""
    catalog = crm_catalog(state)
    archive = getattr(state, "dial_archive", None)
    if archive is not None:
        catalog["archived_dials"] = archive.snapshot()
        catalog["dials_version"] = archive.revision
    else:
        catalog["archived_dials"] = []
        catalog["dials_version"] = 0
    with state.lock:
        in_flight = len([call for call in state.in_flight.values() if call["kind"] == "prospect"])
    catalog["counts"]["calling"] = in_flight
    return catalog


def public_state(state, include_leads=False):
    leads = state.crm.snapshot()
    with state.lock:
        active_call = clear_stale_active(state)
        active_id = active_call.get("lead_id") if active_call else None
        prospect_calls = [call for call in state.in_flight.values() if call["kind"] == "prospect"]
        transcript_call = active_call or next(
            (call for call in prospect_calls if call.get("picked_up") or call["state"] == "live"),
            None,
        )
        current_call = transcript_call or (prospect_calls[0] if prospect_calls else None)
        pending_id = state.pending_outcome
        records = [
            {
                "lead_id": call["lead_id"],
                "name": (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("business"),
                "state": call["state"],
                "caller_id": call.get("caller_id") or "",
                "answered_by": call.get("answered_by") or "",
            }
            for call in prospect_calls
        ]
        callers = list(state.callers)
        view = {
            "running": state.running,
            "paused": state.paused,
            "agent_ready": state.agent_ready,
            "active_lead_id": active_id,
            "pending_outcome_id": pending_id,
            "in_flight": records,
            "caller_ids": callers,
            "current_caller_id": (current_call or {}).get("caller_id") or "",
            "pickup_answered_by": (active_call or {}).get("answered_by") or "",
            "last_error": state.last_error,
            "last_event": state.last_event,
            "activity_log": list(state.activity_log),
            "live_transcript": {
                "lead_id": transcript_call.get("lead_id") if transcript_call else None,
                "partials": list(transcript_call.get("transcript_partials", {}).values()) if transcript_call else [],
                "lines": list(transcript_call.get("transcript_lines", [])) if transcript_call else [],
                "transcribing": bool(transcript_call and transcript_call.get("transcribing")),
                "answered_by": (transcript_call or {}).get("answered_by") or "",
            },
            "session": dict(state.session) if state.session else None,
            "advance_at": state.advance_at,
            "active_call_started_at": active_call.get("connected_at") if active_call else None,
            "manual_lead_id": state.manual_lead_id,
            "tag_call": {
                "lead_id": state.taggable_call.get("lead_id"),
                "outcome": state.taggable_call.get("outcome"),
                "connected_at": state.taggable_call.get("connected_at"),
            } if state.taggable_call else None,
        }
    by_id = {lead["id"]: lead for lead in leads}
    view["active_lead"] = by_id.get(active_id)
    view["pending_outcome"] = by_id.get(pending_id)
    catalog = crm_catalog(state, leads)
    view["leads_version"] = catalog["leads_version"]
    view["timezone_groups"] = catalog["timezone_groups"]
    view["counts"] = dict(catalog["counts"])
    view["counts"]["calling"] = len(view["in_flight"])
    view["selected_timezone"] = state.selected_timezone
    view["selected_business_type"] = getattr(state, "selected_business_type", None) or ""
    view["dial_pool_status"] = resolve_pool_status(getattr(state, "dial_pool_status", None))
    view["caller_id_group"] = resolve_caller_id_group(getattr(state, "caller_id_group", None))
    view["pool"] = catalog["pool"]
    if include_leads:
        view["leads"] = leads
    preferences = state.read_settings()
    view["settings"] = {
        "session_goal": int(preferences["SESSION_GOAL"]),
        "conversation_threshold": int(preferences["CONVERSATION_THRESHOLD_SECONDS"]),
        "auto_advance_delay": int(preferences["AUTO_ADVANCE_DELAY_SECONDS"]),
        "sounds_enabled": preferences["SOUNDS_ENABLED"].lower() == "true",
        "sound_volume": int(preferences["SOUND_VOLUME"]),
        "break_nudge_minutes": int(preferences["BREAK_NUDGE_MINUTES"]),
        "calling_start_hour": int(preferences["CALLING_START_HOUR"]),
        "calling_end_hour": int(preferences["CALLING_END_HOUR"]),
        "opening_script": preferences["OPENING_SCRIPT"],
    }
    view["next_lead"] = by_id.get(view.get("manual_lead_id")) or next(iter(view["pool"]), None)
    view["queue_count"] = state.queue_total if state.session else len(view["pool"])
    view["stage"] = dialer_stage(
        view["running"], view["paused"], active_call,
        bool(pending_id), view["in_flight"],
    )
    session = view.pop("session")
    if session:
        session["current_streak"] = recent_streak(session)
    view["session_stats"] = {
        key: value for key, value in (session or new_session()).items()
        if key != "connect_times"
    }
    view["in_flight"] = [
        {**item, "lead": by_id.get(item["lead_id"])} for item in view["in_flight"]
    ]
    return view


def live_state(state):
    view = public_state(state, include_leads=False)
    view.pop("pool", None)
    return view
