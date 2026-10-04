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

class LifecycleMixin:
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
            if self.session:
                record_disposition(self.session, status)
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
        leads = self.crm.snapshot()
        launches = []
        with self.lock:
            if not self.running or self.paused or not self.agent_ready or self.active or self.pending_outcome:
                return
            active_leads = {call["lead_id"] for call in self.in_flight.values()}
            slots = max(0, 1 - len(self.in_flight))
            pool = [
                lead for lead in self._pool_leads(leads)
                if lead["id"] not in active_leads
                and within_calling_window(
                    lead.get("timezone"),
                    int(self.settings.get("CALLING_START_HOUR", "8")),
                    int(self.settings.get("CALLING_END_HOUR", "21")),
                )
            ]
            for lead in random.sample(pool, min(slots, len(pool))):
                call = self._new_call("prospect", lead)
                call["caller_id"] = self._next_caller()
                launches.append((call, lead["phone"]))
        for call, destination in launches:
            self._launch_call(call, destination)
        self._schedule_calling_window_check()
    def _schedule_calling_window_check(self):
        with self.lock:
            if self.calling_window_timer:
                self.calling_window_timer.cancel()
                self.calling_window_timer = None
            if not self.running or self.paused:
                return
            self.calling_window_timer = threading.Timer(60, self._check_calling_window)
            self.calling_window_timer.daemon = True
            self.calling_window_timer.start()
    def _check_calling_window(self):
        with self.lock:
            self.calling_window_timer = None
            should_fill = self.running and not self.paused and not self.active and not self.pending_outcome
        if should_fill:
            self.fill_slots()
        else:
            self._schedule_calling_window_check()
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
