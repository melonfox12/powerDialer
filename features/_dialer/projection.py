"""Public and live snapshots."""

from features._dialer import calls
from features._dialer.session_stats import dialer_stage, new_session, recent_streak

def public_state(state):
    leads = state.crm.snapshot()
    with state.lock:
        active_id = state.active.get("lead_id") if state.active else None
        active_call = state.active
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
        }
    by_id = {lead["id"]: lead for lead in leads}
    view["active_lead"] = by_id.get(active_id)
    view["pending_outcome"] = by_id.get(pending_id)
    view["leads"] = leads
    groups = state.crm.timezone_groups(leads)
    view["timezone_groups"] = [{"name": name, "count": count} for name, count in groups]
    view["leads_version"] = getattr(state.crm, "revision", 0)
    view["selected_timezone"] = state.selected_timezone
    view["pool"] = calls._pool_leads(state, leads)
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
    view["counts"] = {
        "total": len(leads),
        "new": sum(lead["status"] == "new" for lead in leads),
        "calling": len(view["in_flight"]),
        "booked": sum(lead["status"] == "booked" for lead in leads),
    }
    return view

def live_state(state):
    view = public_state(state)
    view.pop("leads", None)
    view.pop("pool", None)
    return view
