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

class TranscriptMixin:
    def _live_twiml(self, call):
        response = VoiceResponse()
        with self.lock:
            start_transcription = not call.get("transcription_started")
            call["transcription_started"] = True
        if start_transcription:
            self._start_transcription(response, call)
        response.dial().conference(
            self.conference,
            beep="false",
            start_conference_on_enter="true",
            end_conference_on_exit="false",
        )
        return response
    def _start_transcription(self, response, call):
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
        line = {"id": segment_id, "timestamp": timestamp, "speaker": speaker, "text": text, "final": True}
        with self.lock:
            call["transcript_partials"].pop(track or speaker, None)
            lines = call.setdefault("transcript_lines", [])
            lines.append(line)
            del lines[:-80]
        self.record_activity(f"Transcript updated · {speaker}", "transcription")
        return 200, "text/plain", "OK"
    def _call_ended(self, call, params):
        log_entry = None
        with self.lock:
            if call["kind"] == "agent":
                self._agent_call_ended()
                return
            if call.get("end_processed"):
                return
            call["end_processed"] = True
            timer = call.get("answer_detection_timer")
            if timer:
                timer.cancel()
                call["answer_detection_timer"] = None
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
