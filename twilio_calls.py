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
from dialer_session import (
    add_connect, dialer_stage, new_session, recent_streak,
    session_summary, status_for_disposition,
)
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio.twiml.voice_response import VoiceResponse

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}"


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


def read_env(path):
    values = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip().strip('"').strip("'")
    for key in (
        "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
        "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
        "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SECRET_KEY",
    ):
        values.setdefault(key, os.environ.get(key, ""))
    return values


def write_env(path, updates):
    values = read_env(path)
    values.update({key: value.strip() for key, value in updates.items() if value.strip()})
    lines = [f"{key}={value}" for key, value in values.items() if value]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return values


class TwilioDialer:
    def __init__(self, crm, env_path, metrics=None):
        self.crm = crm
        self.env_path = env_path
        self.metrics = metrics
        self.lock = threading.RLock()
        self.running = False
        self.paused = False
        self.agent_ready = False
        self.agent_call_uuid = None
        self.agent_call_token = None
        self.conference = ""
        self.callers = []
        self.caller_index = 0
        self.active = None
        self.pending_outcome = None
        self.calls = {}
        self.in_flight = {}
        self.last_error = ""
        self.last_event = "Ready"
        self.public_base_url = ""
        self.settings = {}
        self.selected_timezone = None
        self.activity_log = []
        self.activity_sequence = 0
        self.session = None
        self.advance_timer = None
        self.advance_at = None
        self.advance_remaining = None

    def _save_session(self):
        if self.metrics and self.session and hasattr(self.metrics, "save_session"):
            self.metrics.save_session(self.session)

    def _pool_leads(self, leads=None):
        leads = self.crm.snapshot() if leads is None else leads
        pool = [lead for lead in leads if lead["status"] == "new"]
        if self.selected_timezone:
            pool = [lead for lead in pool if (lead.get("timezone") or "Unknown") == self.selected_timezone]
        return pool

    def set_timezone_filter(self, timezone):
        timezone = str(timezone or "").strip() or None
        with self.lock:
            self.selected_timezone = timezone
            self.last_event = f"Dialing pool set to {timezone}" if timezone else "Dialing pool set to all timezones"
            should_fill = self.running and self.agent_ready and not self.paused and not self.pending_outcome and not self.active
        if should_fill:
            self.fill_slots()
        return self.public_state()

    def _bump(self, key, amount=1):
        if self.metrics:
            self.metrics.bump(key, amount)

    def record_activity(self, message, source="dialer"):
        with self.lock:
            self.activity_sequence += 1
            self.activity_log.append({
                "id": self.activity_sequence,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "message": str(message),
            })
            del self.activity_log[:-40]

    def public_state(self):
        leads = self.crm.snapshot()
        with self.lock:
            active_id = self.active.get("lead_id") if self.active else None
            active_call = self.active
            pending_id = self.pending_outcome
            records = [
                {"lead_id": call["lead_id"], "state": call["state"]}
                for call in self.in_flight.values() if call["kind"] == "prospect"
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
                "last_error": self.last_error,
                "last_event": self.last_event,
                "activity_log": list(self.activity_log),
                "live_transcript": {
                    "lead_id": active_id,
                    "partials": list(active_call.get("transcript_partials", {}).values()) if active_call else [],
                    "transcribing": bool(active_call and active_call.get("transcribing")),
                },
                "session": dict(self.session) if self.session else None,
                "advance_at": self.advance_at,
            }
        by_id = {lead["id"]: lead for lead in leads}
        state["active_lead"] = by_id.get(active_id)
        state["pending_outcome"] = by_id.get(pending_id)
        state["leads"] = leads
        groups = self.crm.timezone_groups()
        state["timezone_groups"] = [{"name": name, "count": count} for name, count in groups]
        state["selected_timezone"] = self.selected_timezone
        state["pool"] = self._pool_leads(leads)
        state["queue_count"] = len(state["pool"])
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

    def settings_state(self):
        values = read_env(self.env_path)
        return {
            "account_sid": values.get("TWILIO_ACCOUNT_SID", ""),
            "api_key": values.get("TWILIO_API_KEY", ""),
            "twiml_app_sid": values.get("TWILIO_TWIML_APP_SID", ""),
            "public_base_url": values.get("PUBLIC_BASE_URL", ""),
            "has_auth_token": bool(values.get("TWILIO_AUTH_TOKEN")),
            "has_api_secret": bool(values.get("TWILIO_API_SECRET")),
        }

    def validate_webhook(self, url, signature, params):
        values = self.settings or read_env(self.env_path)
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

    def voice_access_token(self):
        self.record_activity("Requesting browser Voice access token", "api")
        values = read_env(self.env_path)
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

    def save_settings(self, data):
        updates = {
            "TWILIO_ACCOUNT_SID": str(data.get("account_sid", "")),
            "TWILIO_AUTH_TOKEN": str(data.get("auth_token", "")),
            "TWILIO_API_KEY": str(data.get("api_key", "")),
            "TWILIO_API_SECRET": str(data.get("api_secret", "")),
            "TWILIO_TWIML_APP_SID": str(data.get("twiml_app_sid", "")),
            "PUBLIC_BASE_URL": str(data.get("public_base_url", "")).rstrip("/"),
        }
        write_env(self.env_path, updates)
        return self.settings_state()

    def start(self):
        with self.lock:
            if self.running:
                return self.public_state()
            self.activity_log.clear()
            self.activity_sequence = 0
        self.record_activity("Start dialing request received", "web")
        values = read_env(self.env_path)
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
        self.settings = values
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
            self.calls.clear()
            self.callers = callers
            self.caller_index = 0
            self.conference = "crm-" + secrets.token_hex(8)
            self.session = new_session()
            self.advance_at = None
            self.advance_remaining = None
            self._save_session()
            self.last_error = ""
            self.last_event = "Connecting computer audio"
            agent_call = self._new_call("agent", None)
            self.agent_call_token = agent_call["token"]
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
            "transcribing": False,
            "transcript_partials": {},
        }
        self.calls[token] = call
        if kind == "prospect":
            self.in_flight[token] = call
            self._bump("dials")
            if self.session:
                self.session["dials"] += 1
                self._save_session()
        return call

    def _url(self, call, action):
        return f"{self.public_base_url}/hooks/{call['token']}/{action}"

    def _launch_call(self, call, destination):
        threading.Thread(target=self._create_call, args=(call, destination), daemon=True).start()

    def _create_call(self, call, destination):
        with self.lock:
            caller = self.callers[self.caller_index % len(self.callers)]
            self.caller_index += 1
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
            elif call_status in ("completed", "busy", "failed", "no-answer", "canceled"):
                action = "hangup"
            else:
                return 200, "text/plain", "OK"
        if action == "ring":
            with self.lock:
                if call["kind"] == "prospect" and not call["handled"] and not call["cancelled"]:
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
            return 200, "application/xml", "<Response><Say>Please hold while we connect you.</Say><Pause length=\"45\"/></Response>"
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
            response = VoiceResponse()
            response.start().transcription(
                status_callback_url=self._url(call, "transcript"),
                name=f"crm-{call['token']}",
                track="both_tracks",
                inbound_track_label="prospect",
                outbound_track_label="agent",
                partial_results=True,
                language_code="en-US",
                speech_model="telephony",
                enable_automatic_punctuation=True,
            )
            response.dial().conference(
                self.conference,
                beep="false",
                start_conference_on_enter="true",
                end_conference_on_exit="false",
            )
            self.record_activity("Starting live two-track transcription", "transcription")
            return 200, "application/xml", str(response)
        return 404, "text/plain", "Unknown callback"

    def _transcription_event(self, call, params):
        event = params.get("TranscriptionEvent", "")
        if event == "transcription-started":
            with self.lock:
                call["transcribing"] = True
            self.record_activity("Live transcript connected", "transcription")
            return 200, "text/plain", "OK"
        if event == "transcription-stopped":
            with self.lock:
                call["transcribing"] = False
                call["transcript_partials"].clear()
            self.record_activity("Live transcript ended", "transcription")
            return 200, "text/plain", "OK"
        if event == "transcription-error":
            error = params.get("TranscriptionError", "Transcription unavailable")
            self.record_activity(f"Live transcription error: {error}", "error")
            return 200, "text/plain", "OK"
        if event != "transcription-content":
            return 200, "text/plain", "OK"
        try:
            data = json.loads(params.get("TranscriptionData", "{}"))
        except (TypeError, ValueError):
            data = {}
        text = str(data.get("transcript", "")).strip()
        if not text:
            return 200, "text/plain", "OK"
        track = params.get("Track", "")
        speaker = "Prospect" if track == "inbound_track" else "Agent" if track == "outbound_track" else "Unknown"
        timestamp = params.get("Timestamp") or datetime.now(timezone.utc).isoformat()
        final = str(params.get("Final", "false")).lower() == "true"
        partial = {"timestamp": timestamp, "speaker": speaker, "text": text, "final": final}
        if not final:
            with self.lock:
                call["transcript_partials"][track or speaker] = partial
            return 200, "text/plain", "OK"

        segment_id = f"{call.get('call_uuid') or call['token']}:{track}:{params.get('SequenceId', timestamp)}"
        try:
            self.crm.append_transcript(call["lead_id"], {
                "id": segment_id,
                "timestamp": timestamp,
                "speaker": speaker,
                "text": text,
            })
        except (KeyError, ValueError, OSError) as exc:
            self.record_activity(f"Could not save transcript segment: {exc}", "error")
            return 200, "text/plain", "OK"
        with self.lock:
            call["transcript_partials"].pop(track or speaker, None)
        self.record_activity(f"Transcript updated · {speaker}", "transcription")
        return 200, "text/plain", "OK"

    def _machine_result(self, call, params):
        answered_by = str(params.get("AnsweredBy") or params.get("MachineDetectionResult") or "unknown").lower()
        self.record_activity(f"Answer detection: {answered_by}", "call")
        result = " ".join(str(params.get(key, "")) for key in (
            "AnsweredBy", "Machine", "machine", "MachineDetection", "MachineDetectionResult", "machine_detection"
        )).lower()
        machine = any(term in result for term in ("machine", "voicemail", "answering service"))
        if machine:
            with self.lock:
                if call["handled"] or call["cancelled"]:
                    return 200, "text/plain", "OK"
                call["handled"] = True
                call["machine"] = True
                self.in_flight.pop(call["token"], None)
                self.last_event = f"Voicemail detected for {call['lead'].get('name') or call['lead']['phone']}"
                self._bump("voicemail")
            self.record_activity("Answering machine detected; prospect marked for later", "call")
            try:
                self.crm.set_status(call["lead_id"], "call")
            except (KeyError, ValueError):
                pass
            if call_uuid := call.get("call_uuid"):
                threading.Thread(target=self._hangup_call, args=(call_uuid,), daemon=True).start()
            threading.Thread(target=self.fill_slots, daemon=True).start()
            return 200, "text/plain", "OK"

        self._select_human(call)
        return 200, "text/plain", "OK"

    def _select_human(self, call):
        with self.lock:
            if call["handled"] or call["cancelled"] or not self.running:
                return
            if self.active or self.pending_outcome:
                call["cancelled"] = True
                call_uuid = call.get("call_uuid")
            else:
                call["handled"] = True
                call["state"] = "connecting"
                self.active = call
                self.last_event = f"Connecting {call['lead'].get('name') or call['lead']['phone']}"
                if self.session:
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

    def _transfer(self, call_uuid, answer_url):
        try:
            twilio_request(self.settings["TWILIO_ACCOUNT_SID"], self.settings["TWILIO_AUTH_TOKEN"], "POST",
                           f"/Calls/{urllib.parse.quote(call_uuid, safe='')}.json", data={
                               "Url": answer_url, "Method": "GET",
                           })
        except TwilioError as exc:
            with self.lock:
                self.last_error = str(exc)

    def _call_ended(self, call, params):
        with self.lock:
            if call["kind"] == "agent":
                self._agent_call_ended()
                return
            if call["machine"] or call["cancelled"] or call["handled"] and self.active is not call:
                return
            was_connected = self.active is call
            call["handled"] = True
            call["state"] = "ended"
            self.in_flight.pop(call["token"], None)
            self.active = None
            outcome_already_chosen = call.get("outcome_chosen")
            if was_connected:
                try:
                    duration = int(float(params.get("CallDuration") or params.get("Duration") or params.get("BillDuration") or 0))
                except (TypeError, ValueError):
                    duration = 0
                self._bump("connected")
                if duration:
                    self._bump("talk_seconds", duration)
                    # A conversation is a human-connected call lasting at least the configured threshold.
                    threshold = int(self.settings.get("CONVERSATION_THRESHOLD_SECONDS", "30"))
                    if duration >= threshold and self.session:
                        self.session["conversations"] += 1
                self._save_session()
            should_fill = False
            should_schedule_advance = False
            if self.running:
                if outcome_already_chosen:
                    self.last_event = "Call ended"
                    should_schedule_advance = True
                else:
                    self.pending_outcome = call["lead_id"]
                    self.last_event = "Choose an outcome before the next calls"
                others = list(self.in_flight.values())
            else:
                others = []
        for other in others:
            self._cancel_call(other)
        if should_schedule_advance:
            self._schedule_advance()
        if should_fill:
            self.fill_slots()

    def _agent_call_ended(self):
        with self.lock:
            self.agent_ready = False
            if self.running and not self.pending_outcome:
                self.paused = True
                self.last_event = "Computer audio disconnected; dialer paused"

    def live_outcome_lead_id(self):
        """The lead id (if any) currently eligible for an outcome: either the call
        that is live on the line right now, or one that just ended and is waiting."""
        with self.lock:
            if self.pending_outcome:
                return self.pending_outcome
            if self.active:
                return self.active.get("lead_id")
            return None

    def choose_outcome(self, lead_id, status, scheduled_until=None):
        if status not in ("call", "disqualified", "booked", "interested", "do_not_call"):
            raise ValueError("Choose a valid call outcome.")
        with self.lock:
            live_call = self.active if self.active and self.active.get("lead_id") == lead_id else None
            if self.pending_outcome != lead_id and not live_call:
                raise ValueError("That prospect is not waiting for an outcome.")
            if live_call:
                live_call["outcome_chosen"] = True
        result = self.crm.set_status(lead_id, status, scheduled_until)
        metric_key = {
            "call": "call_later",
            "interested": "interested",
            "booked": "booked",
        }.get(status, "disqualified")
        self._bump(metric_key)
        with self.lock:
            if status == "booked" and self.session:
                self.session["meetings_booked"] += 1
                self._save_session()
            if self.pending_outcome == lead_id:
                self.pending_outcome = None
            self.last_event = f"{result['name'] or result['phone']} marked {status}"
            can_continue = self.running and not self.paused and not live_call
        if can_continue:
            self._schedule_advance()
        return result

    def update_status(self, lead_id, status=None, scheduled_until=None, disposition=None):
        if disposition:
            status = status_for_disposition(disposition)
        with self.lock:
            is_outcome = self.live_outcome_lead_id() == lead_id and status in (
                "call", "disqualified", "booked", "interested", "do_not_call"
            )
        if is_outcome:
            return self.choose_outcome(lead_id, status, scheduled_until)
        return self.crm.set_status(lead_id, status, scheduled_until)

    def _schedule_advance(self, delay=None):
        with self.lock:
            if not self.running or self.paused or self.pending_outcome or self.active:
                return
            if self.advance_timer:
                self.advance_timer.cancel()
            seconds = max(0, float(delay if delay is not None else self.settings.get("AUTO_ADVANCE_DELAY_SECONDS", 3)))
            self.advance_at = time.time() + seconds
            self.advance_remaining = seconds
            self.advance_timer = threading.Timer(seconds, self._advance_queue)
            self.advance_timer.daemon = True
            self.advance_timer.start()

    def _advance_queue(self):
        with self.lock:
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
            should_fill = self.running and not self.paused and not self.pending_outcome
        if should_fill:
            self.fill_slots()

    def advance_now(self):
        with self.lock:
            if not self.advance_timer or not self.running or self.paused:
                raise ValueError("There is no active auto-advance countdown.")
            self.advance_timer.cancel()
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
        self.fill_slots()
        return self.public_state()

    def fill_slots(self):
        launches = []
        with self.lock:
            if not self.running or self.paused or not self.agent_ready or self.active or self.pending_outcome:
                return
            active_leads = {call["lead_id"] for call in self.in_flight.values()}
            slots = max(0, 1 - len(self.in_flight))
            pool = [lead for lead in self._pool_leads() if lead["id"] not in active_leads]
            for lead in random.sample(pool, min(slots, len(pool))):
                call = self._new_call("prospect", lead)
                launches.append((call, lead["phone"]))
        for call, destination in launches:
            self._launch_call(call, destination)

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
        if should_fill:
            self.fill_slots()
        elif resume_countdown:
            self._schedule_advance(remaining)
        return self.public_state()

    def hangup_active(self):
        with self.lock:
            call = self.active or next(
                (
                    item for item in self.in_flight.values()
                    if item["kind"] == "prospect" and item["state"] == "ringing"
                ),
                None,
            )
            call_uuid = call.get("call_uuid") if call else None
            if call and call is not self.active:
                call["handled"] = True
                call["cancelled"] = True
                call["state"] = "ended"
                self.in_flight.pop(call["token"], None)
                if self.running:
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
            call["handled"] = True
            call["cancelled"] = True
            call["machine"] = True
            call["state"] = "skipped"
            self.active = None
            self.in_flight.pop(call["token"], None)
            self.pending_outcome = None
            call_uuid = call.get("call_uuid")
            continue_dialing = self.running and not self.paused and self.agent_ready
            self.last_event = "Prospect skipped as voicemail"
        self.crm.set_status(call["lead_id"], "call")
        self._bump("call_later")
        self.record_activity("Prospect skipped manually; marked for later", "call")
        if call_uuid:
            threading.Thread(target=self._hangup_call, args=(call_uuid,), daemon=True).start()
        if continue_dialing:
            self.fill_slots()
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
            self.in_flight.clear()
            self.last_event = "Stopped"
            if self.advance_timer:
                self.advance_timer.cancel()
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
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
                )
        return result

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