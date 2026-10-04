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

from twilio_calls.client import ClientMixin, escape_xml, normalize_phone, twilio_request
from twilio_calls.lifecycle import LifecycleMixin
from twilio_calls.settings import SettingsMixin, _preferences, read_env
from twilio_calls.token import TokenMixin
from twilio_calls.transcript import TranscriptMixin
from twilio_calls.webhooks import WebhookMixin


class TwilioDialer(SettingsMixin, ClientMixin, TokenMixin, WebhookMixin, TranscriptMixin, LifecycleMixin):
    def __init__(self, crm, env_path, metrics=None):
        self.crm = crm
        self.env_path = env_path
        self.metrics = metrics
        self.storage_name = "local JSON files"
        self.account_values = {}
        self.account_user_id = None
        self.account_email = ""
        self.token_index = None
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
        self.queue_total = 0
        self.calling_window_timer = None

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
        leads = self.crm.snapshot()
        with self.lock:
            self.selected_timezone = timezone
            if self.session:
                self.queue_total = len(self._pool_leads(leads))
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
        if source != "web":
            debug_event(source, message)

    def public_state(self):
        leads = self.crm.snapshot()
        with self.lock:
            active_id = self.active.get("lead_id") if self.active else None
            active_call = self.active
            prospect_calls = [call for call in self.in_flight.values() if call["kind"] == "prospect"]
            transcript_call = active_call or next(
                (call for call in prospect_calls if call.get("picked_up") or call["state"] in ("live", "listening")),
                None,
            )
            current_call = transcript_call or (prospect_calls[0] if prospect_calls else None)
            pending_id = self.pending_outcome
            records = [
                {
                    "lead_id": call["lead_id"],
                    "name": (call.get("lead") or {}).get("name") or (call.get("lead") or {}).get("business"),
                    "state": call["state"],
                    "caller_id": call.get("caller_id") or "",
                    "answered_by": call.get("answered_by") or "",
                }
                for call in prospect_calls
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
                "current_caller_id": (current_call or {}).get("caller_id") or "",
                "pickup_answered_by": (active_call or {}).get("answered_by") or "",
                "last_error": self.last_error,
                "last_event": self.last_event,
                "activity_log": list(self.activity_log),
                "live_transcript": {
                    "lead_id": transcript_call.get("lead_id") if transcript_call else None,
                    "partials": list(transcript_call.get("transcript_partials", {}).values()) if transcript_call else [],
                    "lines": list(transcript_call.get("transcript_lines", [])) if transcript_call else [],
                    "transcribing": bool(transcript_call and transcript_call.get("transcribing")),
                    "answered_by": (transcript_call or {}).get("answered_by") or "",
                },
                "session": dict(self.session) if self.session else None,
                "advance_at": self.advance_at,
                "active_call_started_at": active_call.get("connected_at") if active_call else None,
            }
        by_id = {lead["id"]: lead for lead in leads}
        state["active_lead"] = by_id.get(active_id)
        state["pending_outcome"] = by_id.get(pending_id)
        state["leads"] = leads
        groups = self.crm.timezone_groups(leads)
        state["timezone_groups"] = [{"name": name, "count": count} for name, count in groups]
        state["leads_version"] = getattr(self.crm, "revision", 0)
        state["selected_timezone"] = self.selected_timezone
        state["pool"] = self._pool_leads(leads)
        preferences = _preferences(self._values())
        state["settings"] = {
            "session_goal": int(preferences["SESSION_GOAL"]),
            "conversation_threshold": int(preferences["CONVERSATION_THRESHOLD_SECONDS"]),
            "auto_advance_delay": int(preferences["AUTO_ADVANCE_DELAY_SECONDS"]),
            "sounds_enabled": preferences["SOUNDS_ENABLED"].lower() == "true",
            "sound_volume": int(preferences["SOUND_VOLUME"]),
            "break_nudge_minutes": int(preferences["BREAK_NUDGE_MINUTES"]),
            "calling_start_hour": int(preferences["CALLING_START_HOUR"]),
            "calling_end_hour": int(preferences["CALLING_END_HOUR"]),
            "opening_script": preferences["OPENING_SCRIPT"],
        }
        state["skipped_unknown_timezone"] = sum(
            local_time(lead.get("timezone")) is None for lead in state["pool"]
        )
        state["skipped_outside_hours"] = sum(
            local_time(lead.get("timezone")) is not None
            and not within_calling_window(
                lead.get("timezone"),
                state["settings"]["calling_start_hour"],
                state["settings"]["calling_end_hour"],
            )
            for lead in state["pool"]
        )
        state["next_lead"] = next(
            (
                lead for lead in state["pool"]
                if within_calling_window(
                    lead.get("timezone"),
                    state["settings"]["calling_start_hour"],
                    state["settings"]["calling_end_hour"],
                )
            ),
            None,
        )
        state["queue_count"] = self.queue_total if self.session else len(state["pool"])
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

    def live_state(self):
        state = self.public_state()
        state.pop("leads", None)
        state.pop("pool", None)
        return state
