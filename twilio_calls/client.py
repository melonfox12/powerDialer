"""Twilio call coordination for the local CRM dialer."""

import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from debug_log import debug_event
from dialer_session import (
    add_connect, dialer_stage, new_session, recent_streak, record_conversation,
    record_disposition,
    local_time, session_summary, status_for_disposition, within_calling_window,
)
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse

class TwilioError(Exception):
    pass


def twilio_request(account_sid, auth_token, method, path, data=None, params=None):
    url = TWILIO_API.format(account_sid=urllib.parse.quote(account_sid, safe="")) + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request.add_header("Authorization", "Basic " + auth)
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = response.read().decode()
            return json.loads(result) if result else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
            message = payload.get("message") or payload.get("error") or str(exc)
        except (ValueError, OSError):
            message = str(exc)
        raise TwilioError(f"Twilio error {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise TwilioError(f"Could not reach Twilio: {exc.reason}") from exc

def normalize_phone(raw):
    text = str(raw or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def escape_xml(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))

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

    @staticmethod
    def _transfer(self, call_uuid, answer_url):
        try:
            twilio_request(self.settings["TWILIO_ACCOUNT_SID"], self.settings["TWILIO_AUTH_TOKEN"], "POST",
                           f"/Calls/{urllib.parse.quote(call_uuid, safe='')}.json", data={
                               "Url": answer_url, "Method": "GET",
                           })
        except TwilioError as exc:
            with self.lock:
                self.last_error = str(exc)
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


def normalize_phone(raw):
    text = str(raw or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def escape_xml(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))
