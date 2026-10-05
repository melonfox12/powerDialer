import threading
import time
from core.dialer_session import session_summary

class ControlsMixin:
    def pause(self):
        with self.lock:
            if not self.running:
                return self.public_state()
            self.paused = not self.paused
            self.last_event = "Paused" if self.paused else "Resumed"
            should_fill = not self.paused and self.agent_ready and not self.pending_outcome
            if self.paused and self.advance_timer:
                self.advance_remaining = max(0, self.advance_at - time.time()) if self.advance_at else 0
                self.advance_timer.cancel()
                self.advance_timer = None
                self.advance_at = None
                should_fill = False
            resume_countdown = not self.paused and self.advance_remaining is not None
            remaining = self.advance_remaining
            should_check_hours = not self.paused
            if self.paused and self.calling_window_timer:
                self.calling_window_timer.cancel()
                self.calling_window_timer = None
        if should_fill:
            self.fill_slots()
        elif resume_countdown:
            self._schedule_advance(remaining)
        if should_check_hours:
            self._schedule_calling_window_check()
        return self.public_state()

    def hangup_active(self):
        with self.lock:
            call = self.active or next(
                (
                    item for item in self.in_flight.values()
                    if item["kind"] == "prospect" and item["state"] in ("ringing", "creating", "listening")
                ),
                None,
            )
            call_uuid = call.get("call_uuid") if call else None
            if call and self.running:
                if call is self.active or call.get("picked_up"):
                    call["wrapping"] = True
                    self.pending_outcome = call["lead_id"]
                    self.last_event = "Call ended; choose a disposition"
                else:
                    call["handled"] = True
                    call["cancelled"] = True
                    call["state"] = "ended"
                    self.in_flight.pop(call["token"], None)
                    self.pending_outcome = call["lead_id"]
                    self.last_event = "Call ended; choose a disposition"
        if call_uuid:
            threading.Thread(target=self._hangup_call, args=(call_uuid,), daemon=True).start()
        return self.public_state()

    def skip_active(self):
        with self.lock:
            call = self.active or next(
                (item for item in self.in_flight.values() if item["kind"] == "prospect"),
                None,
            )
            if not call:
                raise ValueError("There is no prospect call to skip.")
            call_uuid = call.get("call_uuid")
            if call.get("picked_up") or self.active is call:
                call["wrapping"] = True
                call["handled"] = True
                self.pending_outcome = call["lead_id"] if self.running else None
                self.last_event = "Prospect skipped; choose a disposition" if self.running else "Prospect skipped"
            else:
                call["handled"] = True
                call["cancelled"] = True
                call["state"] = "skipped"
                self.active = None
                self.in_flight.pop(call["token"], None)
                self.pending_outcome = call["lead_id"] if self.running else None
                self.last_event = "Prospect skipped; choose a disposition" if self.running else "Prospect skipped"
        if not self.running:
            self.crm.set_status(call["lead_id"], "call")
            self._bump("call_later")
        self.record_activity("Prospect skipped; choose a disposition", "call")
        if call_uuid:
            threading.Thread(target=self._hangup_call, args=(call_uuid,), daemon=True).start()
        return self.public_state()

    def stop(self):
        with self.lock:
            calls = list(self.calls.values())
            for call in calls:
                call["cancelled"] = True
            self.running = False
            self.paused = False
            self.agent_ready = False
            self.active = None
            self.pending_outcome = None
            self.manual_lead_id = None
            self.in_flight.clear()
            self.last_event = "Stopped"
            if self.advance_timer:
                self.advance_timer.cancel()
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
            if self.calling_window_timer:
                self.calling_window_timer.cancel()
            self.calling_window_timer = None
            summary = session_summary(self.session) if self.session else None
            if summary:
                self.session.update(summary)
                self._save_session()
        self.record_activity("Dialer stopped", "call")
        for call in calls:
            if call.get("call_uuid"):
                threading.Thread(target=self._hangup_call, args=(call["call_uuid"],), daemon=True).start()
        result = self.public_state()
        if summary:
            result["session_summary"] = summary
            if self.metrics:
                result["previous_session"] = next(
                    (item for item in self.metrics.recent_sessions(5) if item.get("id") != summary["id"]),
                    None,
                    ) if hasattr(self.metrics, "recent_sessions") else None
        return result
