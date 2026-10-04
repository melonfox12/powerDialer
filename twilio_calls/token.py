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

class TokenIndex:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens = {}

    def register(self, token, dialer):
        with self._lock:
            self._tokens[token] = dialer

    def forget(self, token):
        with self._lock:
            self._tokens.pop(token, None)

    def lookup(self, token):
        if not token:
            return None
        with self._lock:
            return self._tokens.get(token)

class TokenMixin:
    def _watch_token(self, token):
        index = self.token_index
        if index is not None:
            index.register(token, self)
    def _release_tokens(self):
        index = self.token_index
        if index is None:
            return
        for token in list(self.calls):
            index.forget(token)
    def voice_access_token(self):
        self.record_activity("Requesting browser Voice access token", "api")
        values = self._values()
        required = (
            "TWILIO_ACCOUNT_SID", "TWILIO_API_KEY", "TWILIO_API_SECRET",
            "TWILIO_TWIML_APP_SID",
        )
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError("Complete Twilio Account SID, API Key SID, API Key Secret, and TwiML App SID in Settings.")
        token = AccessToken(
            values["TWILIO_ACCOUNT_SID"],
            values["TWILIO_API_KEY"],
            values["TWILIO_API_SECRET"],
            identity="prospect_desk_agent",
            ttl=3600,
        )
        token.add_grant(VoiceGrant(outgoing_application_sid=values["TWILIO_TWIML_APP_SID"]))
        return token.to_jwt()
    def start(self):
        with self.lock:
            if self.running:
                return self.public_state()
            self.activity_log.clear()
            self.activity_sequence = 0
        self.record_activity("Start dialing request received", "web")
        values = self._values()
        required = (
            "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
            "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
        )
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError("Complete Twilio account credentials, API key, TwiML App, and public HTTPS URL in Settings.")
        public_url = values["PUBLIC_BASE_URL"].rstrip("/")
        parsed = urllib.parse.urlsplit(public_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("Public webhook URL must start with https://")
        preferences = _preferences(values)
        self.settings = {**values, **preferences}
        self.public_base_url = public_url
        self.record_activity("Checking Twilio account for voice-capable caller IDs", "api")
        numbers = twilio_request(values["TWILIO_ACCOUNT_SID"], values["TWILIO_AUTH_TOKEN"],
                                 "GET", "/IncomingPhoneNumbers.json", params={"PageSize": 1000})
        callers = []
        for item in numbers.get("incoming_phone_numbers", []):
            if not item.get("capabilities", {}).get("voice", False):
                continue
            caller = normalize_phone(item.get("phone_number", ""))
            if caller and caller not in callers:
                callers.append(caller)
        if not callers:
            raise ValueError("No voice-enabled Twilio phone numbers were found on this account.")
        self.record_activity(f"Twilio ready: {len(callers)} caller ID(s) available", "api")
        eligible = self._pool_leads()
        if not eligible:
            where = f" in the {self.selected_timezone} timezone" if self.selected_timezone else ""
            raise ValueError(f"There are no prospects with new status{where} in the caller pool.")
        with self.lock:
            self.running = True
            self.paused = False
            self.agent_ready = False
            self.agent_call_uuid = None
            self.pending_outcome = None
            self.active = None
            self.in_flight.clear()
            self._release_tokens()
            self.calls.clear()
            self.callers = callers
            self.caller_index = 0
            self.conference = "crm-" + secrets.token_hex(8)
            self.session = new_session(goal=int(preferences["SESSION_GOAL"]))
            self.queue_total = len(eligible)
            self.advance_at = None
            self.advance_remaining = None
            self._save_session()
            self.last_error = ""
            self.last_event = "Connecting computer audio"
            agent_call = self._new_call("agent", None)
            self.agent_call_token = agent_call["token"]
            self._schedule_calling_window_check()
        state = self.public_state()
        state["client_call_token"] = agent_call["token"]
        return state
    def handle_client_voice(self, params):
        token = params.get("CallToken", "")
        with self.lock:
            call = self.calls.get(token)
            if not call or call["kind"] != "agent" or call["cancelled"] or not self.running:
                return 200, "application/xml", "<Response><Hangup/></Response>"
            call_uuid = params.get("CallSid", "")
            if call_uuid:
                call["call_uuid"] = call_uuid
                self.agent_call_uuid = call_uuid
            self.agent_ready = True
            self.last_event = "Computer audio connected"
        self.record_activity("Browser audio joined the conference", "call")
        threading.Thread(target=self.fill_slots, daemon=True).start()
        xml = (
            f'<Response><Dial action="{escape_xml(self._url(call, "agent-ended"))}" method="POST">'
            '<Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="true">'
            f'{escape_xml(self.conference)}</Conference></Dial></Response>'
        )
        return 200, "application/xml", xml
    def _new_call(self, kind, lead):
        token = secrets.token_urlsafe(24)
        call = {
            "token": token,
            "kind": kind,
            "lead_id": lead["id"] if lead else None,
            "lead": lead,
            "call_uuid": None,
            "state": "creating" if kind == "prospect" else "calling agent",
            "handled": False,
            "cancelled": False,
            "machine": False,
            "transcribing": False,
            "transcript_partials": {},
            "transcription_started": False,
            "answer_detection_timer": None,
            "caller_id": "",
            "answered_by": "",
            "picked_up": False,
            "connect_counted": False,
            "transcript_lines": [],
            "end_processed": False,
        }
        self.calls[token] = call
        self._watch_token(token)
        if kind == "prospect":
            self.in_flight[token] = call
            self._bump("dials")
            if self.session:
                self.session["dials"] += 1
                self._save_session()
        return call
