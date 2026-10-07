"""Dialer state and the call record shape.

A call stays a dict. `_new_call` in queue.py builds it. Keys: token, kind,
lead_id, lead, call_uuid, state, handled, cancelled, machine, transcribing,
transcript_partials, transcription_started, caller_id, answered_by, picked_up,
connect_counted, transcript_lines, end_processed. outcome_chosen and wrapping
are set later by outcome and end handlers. connected_at is set on pickup.
"""

import threading
from datetime import datetime, timezone

from shared.infra import debug_event


class DialerState:
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
        self.metrics_lock = threading.Lock()
        self.pending_bumps = []
        self.session_save_pending = False
        self.session_version = 0
        self.saved_session_version = 0
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
        self.manual_lead_id = None


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

