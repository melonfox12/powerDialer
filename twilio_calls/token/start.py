import secrets
import urllib.error
import urllib.parse
import urllib.request
from core.dialer_session import new_session
from twilio_calls.client import normalize_phone, twilio_request
from twilio_calls.settings import _preferences

class StartMixin:
    def start(self, priority_lead_id=None):
        priority = self._dialable_lead(priority_lead_id) if priority_lead_id else None
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
        if not eligible and priority is None:
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
            self.manual_lead_id = priority["id"] if priority else None
            pinned_extra = 1 if priority and all(item["id"] != priority["id"] for item in eligible) else 0
            self.queue_total = len(eligible) + pinned_extra
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
