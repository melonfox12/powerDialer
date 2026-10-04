from datetime import datetime, timezone
from core.dialer_session import add_connect

class LiveMixin:
    def enter_live_line(self):
        with self.lock:
            if self.active and self.active.get("picked_up"):
                already = True
                call = None
            else:
                already = False
                call = next(
                    (
                        item for item in self.in_flight.values()
                        if item["kind"] == "prospect" and item["state"] == "listening"
                    ),
                    None,
                )
        if already:
            return self.public_state()
        if call is None:
            raise ValueError("There is no prospect line waiting to be connected.")
        self.record_activity("Rep kept the answered line", "call")
        self._select_human(call)
        return self.public_state()

    def _select_human(self, call):
        with self.lock:
            if call["handled"] or call["cancelled"] or not self.running:
                return
            if self.active or self.pending_outcome:
                call["cancelled"] = True
                call_uuid = call.get("call_uuid")
            else:
                call["handled"] = True
                call["picked_up"] = True
                call["state"] = "live"
                call["connected_at"] = call.get("connected_at") or datetime.now(timezone.utc).isoformat()
                timer = call.get("answer_detection_timer")
                if timer:
                    timer.cancel()
                    call["answer_detection_timer"] = None
                self.active = call
                self.last_event = f"Connecting {call['lead'].get('name') or call['lead']['phone']}"
                if self.session:
                    # Only an answer classified as human is a connect; AMD machine calls do not count.
                    add_connect(self.session)
                    self._save_session()
                call_uuid = call.get("call_uuid")
                others = [item for item in self.in_flight.values() if item is not call]
        if not self.active or self.active is not call:
            if call_uuid:
                self._hangup_call(call_uuid)
            return
        for other in others:
            self._cancel_call(other)
        self.record_activity(f"Human detected; connecting {call['lead'].get('name') or 'prospect'}", "call")
        if call_uuid:
            self._transfer(call_uuid, self._url(call, "winner"))
