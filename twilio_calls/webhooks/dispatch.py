import threading
from twilio_calls.client import escape_xml

class DispatchMixin:
    @staticmethod
    def _uuid(params):
        return params.get("CallSid") or params.get("call_uuid") or ""

    def handle_webhook(self, token, action, params):
        with self.lock:
            call = self.calls.get(token)
            if not call:
                return 200, "application/xml", "<Response><Hangup/></Response>"
            call_uuid = self._uuid(params)
            if call_uuid:
                call["call_uuid"] = call_uuid
                if call["kind"] == "agent":
                    self.agent_call_uuid = call_uuid

            self.record_activity(f"Call callback: {action}", "webhook")
        if action == "status":
            call_status = params.get("CallStatus", "").lower()
            if call_status == "ringing":
                action = "ring"
            elif call_status == "answered" and call["kind"] == "prospect":
                if not call.get("cancelled"):
                    self._pickup(call)
                return 200, "text/plain", "OK"
            elif call_status in ("completed", "busy", "failed", "no-answer", "canceled"):
                action = "hangup"
            else:
                return 200, "text/plain", "OK"
        if action == "ring":
            with self.lock:
                if (
                    call["kind"] == "prospect"
                    and not call["handled"]
                    and not call["cancelled"]
                    and not call.get("picked_up")
                ):
                    call["state"] = "ringing"
            if call.get("cancelled") and call_uuid:
                self._hangup_call(call_uuid)
            return 200, "text/plain", "OK"
        if action == "answer" and call["kind"] == "agent":
            with self.lock:
                self.agent_ready = True
                self.last_event = "Computer audio connected"
            threading.Thread(target=self.fill_slots, daemon=True).start()
            xml = ("<Response><Say>Dialer connected. Stay on the line.</Say><Dial>"
                   '<Conference beep="false" startConferenceOnEnter="true" '
                   f'endConferenceOnExit="true">{escape_xml(self.conference)}</Conference></Dial></Response>')
            return 200, "application/xml", xml
        if action == "answer":
            if call["kind"] != "prospect" or call["cancelled"] or not self.running:
                return 200, "application/xml", "<Response><Hangup/></Response>"
            self._pickup(call)
            return 200, "application/xml", str(self._live_twiml(call))
        if action == "machine":
            return self._machine_result(call, params)
        if action == "transcript":
            return self._transcription_event(call, params)
        if action == "hangup":
            self._call_ended(call, params)
            return 200, "text/plain", "OK"
        if action == "agent-ended" and call["kind"] == "agent":
            self._agent_call_ended()
            return 200, "application/xml", "<Response/>"
        if action == "winner":
            self.record_activity("Prospect joined the live line", "call")
            return 200, "application/xml", str(self._live_twiml(call))
        return 404, "text/plain", "Unknown callback"
