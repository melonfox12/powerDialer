import base64
import hashlib
import hmac
import threading
import urllib.error
import urllib.parse
import urllib.request
from twilio_calls.client.http import TwilioError
from twilio_calls.client.http import twilio_request

class ClientMixin:
    def validate_webhook(self, url, signature, params):
        values = self.settings or self._values()
        auth_token = values.get("TWILIO_AUTH_TOKEN", "")
        if not auth_token or not signature:
            return False
        signed = url
        for key in sorted(params):
            values = params[key]
            if not isinstance(values, (list, tuple)):
                values = [values]
            for value in sorted(str(value) for value in values):
                signed += key + value
        digest = hmac.new(auth_token.encode(), signed.encode(), hashlib.sha1).digest()
        expected = base64.b64encode(digest).decode()
        return hmac.compare_digest(expected, signature)

    def _url(self, call, action):
        return f"{self.public_base_url}/hooks/{call['token']}/{action}"

    def _next_caller(self):
        with self.lock:
            if not self.callers:
                raise TwilioError("No voice-enabled Twilio numbers are available.")
            caller = self.callers[self.caller_index % len(self.callers)]
            self.caller_index += 1
            return caller

    def _launch_call(self, call, destination):
        if not call.get("caller_id"):
            call["caller_id"] = self._next_caller()
        threading.Thread(target=self._create_call, args=(call, destination), daemon=True).start()

    def _create_call(self, call, destination):
        caller = call.get("caller_id") or self._next_caller()
        call["caller_id"] = caller
        data = {
            "To": destination,
            "From": caller,
            "Url": self._url(call, "answer"),
            "Method": "GET",
            "StatusCallback": self._url(call, "status"),
            "StatusCallbackMethod": "POST",
            "StatusCallbackEvent": ["initiated", "ringing", "answered", "completed"],
            "Timeout": "25",
            "TimeLimit": "14400",
        }
        if call["kind"] == "prospect":
            data.update({
                "MachineDetection": "Enable",
                "AsyncAmd": "true",
                "MachineDetectionTimeout": "12",
                "MachineDetectionSpeechEndThreshold": "800",
                "AsyncAmdStatusCallback": self._url(call, "machine"),
                "AsyncAmdStatusCallbackMethod": "POST",
            })
        lead_name = (call.get("lead") or {}).get("name") or "prospect"
        self.record_activity(f"Requesting Twilio call for {lead_name}", "api")
        try:
            result = twilio_request(self.settings["TWILIO_ACCOUNT_SID"], self.settings["TWILIO_AUTH_TOKEN"],
                                    "POST", "/Calls.json", data=data)
            call_uuid = result.get("sid")
            if not call_uuid:
                raise TwilioError("Twilio did not return a call SID.")
            with self.lock:
                call["call_uuid"] = call_uuid
                if call["kind"] == "agent":
                    self.agent_call_uuid = call_uuid
                cancelled = call["cancelled"]
                if not cancelled:
                    self.last_event = "Ringing agent" if call["kind"] == "agent" else "Calling prospects"
            if cancelled:
                self._hangup_call(call_uuid)
            else:
                self.record_activity(f"Twilio call accepted for {lead_name}", "call")
        except TwilioError as exc:
            with self.lock:
                if call["kind"] == "agent":
                    self.running = False
                else:
                    self.in_flight.pop(call["token"], None)
                    call["handled"] = True
                    self._bump("failed")
                self.paused = True
                self.last_error = str(exc)
                self.last_event = "Call request failed"
            self.record_activity(f"Twilio call failed: {exc}", "error")

    def _cancel_call(self, call):
        with self.lock:
            if call["cancelled"]:
                return
            call["cancelled"] = True
            call["state"] = "cancelled"
            self.in_flight.pop(call["token"], None)
            call_uuid = call.get("call_uuid")
        if call_uuid:
            threading.Thread(target=self._hangup_call, args=(call_uuid,), daemon=True).start()

    def _hangup_call(self, call_uuid):
        try:
            twilio_request(self.settings["TWILIO_ACCOUNT_SID"], self.settings["TWILIO_AUTH_TOKEN"], "POST",
                           f"/Calls/{urllib.parse.quote(call_uuid, safe='')}.json", data={"Status": "completed"})
        except (TwilioError, KeyError):
            pass
