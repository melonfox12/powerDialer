"""Dialer entry. Part import order, low to high:

twilio_api → state → session_stats → calls → projection → slots → timing → queue → _call_events → call_events → outcomes.

slots imports calls and session_stats. timing imports slots and projection. queue imports calls, then slots, then timing. call_events imports pickup, transcript, then ended. projection imports calls and does not import anything above it. Nothing in features/_dialer imports this module. Parts read credentials and preferences through read_values and read_settings.
"""

import urllib.parse

from features import settings as settings_feature
from features._dialer import call_events, outcomes, projection, queue, twilio_api
from features._dialer._call_events import ended, pickup, transcript
from features._dialer import calls, session_stats, slots, timing
from features._dialer.state import DialerState
from features._dialer.twilio_api import TokenIndex, TwilioError

__all__ = ["Dialer", "ROUTES", "TokenIndex", "TwilioError"]


class Dialer(DialerState):
    def read_values(self):
        return settings_feature.values(self.env_path, self.account_values, signed_in=bool(self.account_user_id))

    def read_settings(self):
        current = self.read_values()
        return {**current, **settings_feature.preferences(current)}

    def public_state(self):
        return projection.public_state(self)

    def live_state(self):
        return projection.live_state(self)

    def set_timezone_filter(self, timezone):
        return queue.set_timezone_filter(self, timezone)

    def start(self, priority_lead_id=None):
        return queue.start(self, priority_lead_id)

    def _new_call(self, kind, lead):
        call = calls._new_call(self, kind, lead)
        session_stats._flush_metrics(self)
        return call

    def dial_lead(self, lead_id):
        return queue.dial_lead(self, lead_id)

    def pause(self):
        return queue.pause(self)

    def stop(self):
        return queue.stop(self)

    def fill_slots(self):
        return slots.fill_slots(self)

    def advance_now(self):
        return timing.advance_now(self)

    def handle_webhook(self, token, action, params):
        return call_events.handle_webhook(self, token, action, params)

    def handle_client_voice(self, params):
        return call_events.handle_client_voice(self, params)

    def hangup_active(self):
        return call_events.hangup_active(self)

    def skip_active(self):
        return call_events.skip_active(self)

    def _pickup(self, call):
        return pickup._pickup(self, call)

    def _machine_result(self, call, params):
        return pickup._machine_result(self, call, params)

    def _transcription_event(self, call, params):
        return transcript._transcription_event(self, call, params)

    def _call_ended(self, call, params):
        return ended._call_ended(self, call, params)

    def choose_outcome(self, lead_id, status, scheduled_until=None):
        return outcomes.choose_outcome(self, lead_id, status, scheduled_until)

    def update_status(self, lead_id, status=None, scheduled_until=None, disposition=None):
        return outcomes.update_status(self, lead_id, status, scheduled_until, disposition)

    def validate_webhook(self, url, signature, params):
        return twilio_api.validate_webhook(self, url, signature, params)

    def voice_access_token(self):
        return twilio_api.voice_access_token(self)

    def settings_state(self):
        return settings_feature.settings_state(
            self.env_path,
            self.account_values,
            getattr(self, "storage_name", "local JSON files"),
            getattr(self, "account_email", ""),
            signed_in=bool(self.account_user_id),
        )

    def save_settings(self, data):
        save_remote = None
        saver = getattr(self, "settings_saver", None)
        if saver:
            def save_remote(_stored, saver=saver):
                saver(self)
        parsed = settings_feature.save_settings(
            self.env_path, self.account_values, self.account_user_id, data, save_remote,
        )
        with self.lock:
            self.settings.update(parsed)
        return self.settings_state()


def get_state(request):
    try:
        request.send_json(200, request.account.dialer.public_state())
    except OSError as exc:
        request.report_storage_error(exc)


def get_live(request):
    try:
        request.send_json(200, request.account.dialer.live_state())
    except OSError as exc:
        request.report_storage_error(exc)


def get_voice_token(request):
    try:
        request.send_json(200, {"token": request.account.dialer.voice_access_token()})
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})


def post_timezone(request, data):
    request.send_json(200, request.account.dialer.set_timezone_filter(data.get("timezone")))


def post_start(request):
    request.send_json(200, request.account.dialer.start())


def post_pause(request):
    request.send_json(200, request.account.dialer.pause())


def post_stop(request):
    request.send_json(200, request.account.dialer.stop())


def post_hangup(request):
    request.send_json(200, request.account.dialer.hangup_active())


def post_skip(request):
    request.send_json(200, request.account.dialer.skip_active())


def post_advance(request):
    request.send_json(200, request.account.dialer.advance_now())


def post_dial(request):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/dial"))
    request.send_json(200, request.account.dialer.dial_lead(lead_id))


def post_status(request, data):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/status"))
    dialer = request.account.dialer
    lead = dialer.update_status(
        lead_id, data.get("status"), data.get("scheduled_until"), data.get("disposition"),
    )
    request.send_json(200, {"lead": lead, "state": dialer.public_state()})


ROUTES = [
    ("GET", "/api/state", get_state, "GET reads"),
    ("GET", "/api/live", get_live, "GET reads"),
    ("GET", "/api/voice-token", get_voice_token, "voice-token"),
    ("POST", "/api/timezone", post_timezone, "POST"),
    ("POST", "/api/start", post_start, "POST"),
    ("POST", "/api/pause", post_pause, "POST"),
    ("POST", "/api/stop", post_stop, "POST"),
    ("POST", "/api/hangup", post_hangup, "POST"),
    ("POST", "/api/skip", post_skip, "POST"),
    ("POST", "/api/advance", post_advance, "POST"),
    ("POST", "/api/leads/{id}/dial", post_dial, "POST"),
    ("POST", "/api/leads/{id}/status", post_status, "POST"),
]
