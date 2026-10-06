from core.dialer_session import dialer_stage, new_session, recent_streak
from twilio_calls.settings import _preferences

class StateMixin:
    def public_state(self):
        leads = self.crm.snapshot()
        with self.lock:
            active_id = self.active.get("lead_id") if self.active else None
            active_call = self.active
            prospect_calls = [call for call in self.in_flight.values() if call["kind"] == "prospect"]
            transcript_call = active_call or next(
                (call for call in prospect_calls if call.get("picked_up") or call["state"] == "live"),
                None,
            )
            current_call = transcript_call or (prospect_calls[0] if prospect_calls else None)
            pending_id = self.pending_outcome
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
            callers = list(self.callers)
            state = {
                "running": self.running,
                "paused": self.paused,
                "agent_ready": self.agent_ready,
                "active_lead_id": active_id,
                "pending_outcome_id": pending_id,
                "in_flight": records,
                "caller_ids": callers,
                "current_caller_id": (current_call or {}).get("caller_id") or "",
                "pickup_answered_by": (active_call or {}).get("answered_by") or "",
                "last_error": self.last_error,
                "last_event": self.last_event,
                "activity_log": list(self.activity_log),
                "live_transcript": {
                    "lead_id": transcript_call.get("lead_id") if transcript_call else None,
                    "partials": list(transcript_call.get("transcript_partials", {}).values()) if transcript_call else [],
                    "lines": list(transcript_call.get("transcript_lines", [])) if transcript_call else [],
                    "transcribing": bool(transcript_call and transcript_call.get("transcribing")),
                    "answered_by": (transcript_call or {}).get("answered_by") or "",
                },
                "session": dict(self.session) if self.session else None,
                "advance_at": self.advance_at,
                "active_call_started_at": active_call.get("connected_at") if active_call else None,
                "manual_lead_id": self.manual_lead_id,
            }
        by_id = {lead["id"]: lead for lead in leads}
        state["active_lead"] = by_id.get(active_id)
        state["pending_outcome"] = by_id.get(pending_id)
        state["leads"] = leads
        groups = self.crm.timezone_groups(leads)
        state["timezone_groups"] = [{"name": name, "count": count} for name, count in groups]
        state["leads_version"] = getattr(self.crm, "revision", 0)
        state["selected_timezone"] = self.selected_timezone
        state["pool"] = self._pool_leads(leads)
        preferences = _preferences(self._values())
        state["settings"] = {
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
        state["next_lead"] = by_id.get(state.get("manual_lead_id")) or next(iter(state["pool"]), None)
        state["queue_count"] = self.queue_total if self.session else len(state["pool"])
        state["stage"] = dialer_stage(
            state["running"], state["paused"], active_call,
            bool(pending_id), state["in_flight"],
        )
        session = state.pop("session")
        if session:
            session["current_streak"] = recent_streak(session)
        state["session_stats"] = {
            key: value for key, value in (session or new_session()).items()
            if key != "connect_times"
        }
        state["in_flight"] = [
            {**item, "lead": by_id.get(item["lead_id"])} for item in state["in_flight"]
        ]
        state["counts"] = {
            "total": len(leads),
            "new": sum(lead["status"] == "new" for lead in leads),
            "calling": len(state["in_flight"]),
            "booked": sum(lead["status"] == "booked" for lead in leads),
        }
        return state
