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

from twilio_calls.client import TwilioError, escape_xml, normalize_phone, twilio_request
from twilio_calls.settings import DIALER_DEFAULTS, _preferences, read_env, write_env

class WebhookMixin:
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
    def _pickup(self, call):
        """Bridge any answer, including voicemail, so the rep can hear it."""
        with self.lock:
            if call["kind"] != "prospect" or call["cancelled"] or not self.running:
                return False
            if call.get("picked_up"):
                return False
            call["picked_up"] = True
            call["state"] = "live"
            call["connected_at"] = datetime.now(timezone.utc).isoformat()
            timer = call.get("answer_detection_timer")
            if timer:
                timer.cancel()
                call["answer_detection_timer"] = None
            self.active = call
            if self.session and not call.get("connect_counted"):
                add_connect(self.session)
                call["connect_counted"] = True
                self._save_session()
            name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
            caller = call.get("caller_id") or ""
            self.last_event = f"Picked up {name}" + (f" from {caller}" if caller else "")
            others = [item for item in self.in_flight.values() if item is not call]
        for other in others:
            self._cancel_call(other)
        self.record_activity(f"Pickup on the line: {name}. Stay on it or skip.", "call")
        return True
    def _machine_result(self, call, params):
        answered_by = str(params.get("AnsweredBy") or params.get("MachineDetectionResult") or "unknown").lower()
        self.record_activity(f"Answer detection: {answered_by}", "call")
        result = " ".join(str(params.get(key, "")) for key in (
            "AnsweredBy", "Machine", "machine", "MachineDetection", "MachineDetectionResult", "machine_detection"
        )).lower()
        machine = any(term in result for term in ("machine", "voicemail", "fax", "answering service"))
        human = "human" in result and not machine
        label = "voicemail" if machine else "human" if human else "unknown"
        with self.lock:
            if call["cancelled"] or call.get("end_processed"):
                return 200, "text/plain", "OK"
            call["answered_by"] = label
            if machine:
                call["machine"] = True
                if not call.get("machine_counted"):
                    call["machine_counted"] = True
                    self._bump("voicemail")
            name = (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("phone") or "prospect"
            if label == "voicemail":
                self.last_event = f"Voicemail on the line: {name}"
            elif label == "human":
                self.last_event = f"Live voice: {name}"
            else:
                self.last_event = f"On the line: {name}"
        if not call.get("picked_up"):
            self._pickup(call)
        self.record_activity(
            "Voicemail is on the line" if label == "voicemail"
            else "Live voice is on the line" if label == "human"
            else "Pickup is on the line",
            "call",
        )
        return 200, "text/plain", "OK"
    def _answer_detection_timeout(self, call):
        """Older builds hung up when detection was slow. Any pickup now stays connected."""
        with self.lock:
            timer = call.get("answer_detection_timer")
            if timer:
                timer.cancel()
            call["answer_detection_timer"] = None
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
