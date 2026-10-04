import threading
from datetime import datetime, timezone
from core.debug_log import debug_event

class CoreMixin:
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

    def live_state(self):
        state = self.public_state()
        state.pop("leads", None)
        state.pop("pool", None)
        return state
