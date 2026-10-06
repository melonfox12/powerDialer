from datetime import datetime, timezone
from core.dialer_session import record_conversation

class EndedMixin:
    def _call_ended(self, call, params):
        log_entry = None
        with self.lock:
            if call["kind"] == "agent":
                self._agent_call_ended()
                return
            if call.get("end_processed"):
                return
            call["end_processed"] = True
            if call["cancelled"] and not call.get("picked_up"):
                self.in_flight.pop(call["token"], None)
                if self.active is call:
                    self.active = None
                return
            was_connected = bool(call.get("picked_up")) or self.active is call
            call["handled"] = True
            call["state"] = "ended"
            self.in_flight.pop(call["token"], None)
            if self.active is call:
                self.active = None
            outcome_already_chosen = call.get("outcome_chosen")
            pending_already = self.pending_outcome == call.get("lead_id")
            duration = 0
            if was_connected:
                try:
                    duration = int(float(params.get("CallDuration") or params.get("Duration") or params.get("BillDuration") or 0))
                except (TypeError, ValueError):
                    duration = 0
                self._bump("connected")
                if duration:
                    self._bump("talk_seconds", duration)
                    threshold = int(self.settings.get("CONVERSATION_THRESHOLD_SECONDS", "30"))
                    if self.session and call.get("answered_by") != "voicemail":
                        record_conversation(self.session, duration, threshold)
                self._save_session()
                log_entry = {
                    "id": call.get("call_uuid") or call["token"],
                    "started_at": call.get("connected_at") or "",
                    "ended_at": datetime.now(timezone.utc).isoformat(),
                    "caller_id": call.get("caller_id") or "",
                    "answered_by": call.get("answered_by") or "unknown",
                    "duration_seconds": duration,
                    "transcript_lines": len(call.get("transcript_lines") or []),
                }
            should_schedule_advance = False
            if self.running and was_connected:
                if outcome_already_chosen:
                    self.last_event = "Call ended"
                    should_schedule_advance = not pending_already and not self.pending_outcome
                elif not pending_already:
                    self.pending_outcome = call["lead_id"]
                    self.last_event = "Choose an outcome before the next calls"
            elif self.running and not was_connected and not pending_already and not outcome_already_chosen:
                self.last_event = "No answer"
                should_schedule_advance = True
            others = list(self.in_flight.values()) if self.running else []
        for other in others:
            self._cancel_call(other)
        if log_entry and call.get("lead_id"):
            try:
                self.crm.append_call_log(call["lead_id"], log_entry)
            except (KeyError, ValueError, OSError) as exc:
                self.record_activity(f"Could not log the call: {exc}", "error")
        if should_schedule_advance:
            self._schedule_advance()

    def _agent_call_ended(self):
        with self.lock:
            self.agent_ready = False
            if self.running and not self.pending_outcome:
                self.paused = True
                self.last_event = "Computer audio disconnected; dialer paused"
