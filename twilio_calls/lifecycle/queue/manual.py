class ManualDialMixin:
    def dial_lead(self, lead_id):
        lead = self._dialable_lead(lead_id)
        name = lead.get("name") or lead.get("phone") or "Prospect"
        with self.lock:
            running = self.running
        if not running:
            state = self.start(priority_lead_id=lead["id"])
            if state.get("client_call_token"):
                state["dial_status"] = "started"
                self.record_activity(f"Manual dial started for {name}", "web")
                return state
        return self._pin_manual_dial(lead, name)

    def _dialable_lead(self, lead_id):
        lead_id = str(lead_id or "").strip()
        if not lead_id:
            raise ValueError("Choose a prospect to dial.")
        lead = next((item for item in self.crm.snapshot() if item["id"] == lead_id), None)
        if lead is None:
            raise KeyError("Prospect not found")
        if not str(lead.get("phone") or "").strip():
            raise ValueError("This prospect has no phone number.")
        if lead.get("status") == "do_not_call":
            raise ValueError("This prospect is marked do not call.")
        return lead

    def _claim_manual_lead(self, leads, active_leads):
        lead_id = self.manual_lead_id
        if not lead_id:
            return None
        lead = next((item for item in leads if item["id"] == lead_id), None)
        blocked = (
            not lead
            or not lead.get("phone")
            or lead.get("status") == "do_not_call"
            or lead["id"] in active_leads
        )
        if blocked:
            self.manual_lead_id = None
            return None
        self.manual_lead_id = None
        return lead

    def _pin_manual_dial(self, lead, name):
        with self.lock:
            on_line = (
                (self.active and self.active.get("lead_id") == lead["id"])
                or self.pending_outcome == lead["id"]
                or any(call.get("lead_id") == lead["id"] for call in self.in_flight.values())
            )
            if on_line:
                status = "already"
            else:
                self.manual_lead_id = lead["id"]
                if self.advance_timer:
                    self.advance_timer.cancel()
                    self.advance_timer = None
                self.advance_at = None
                self.advance_remaining = None
                idle = not self.active and not self.pending_outcome and not self.in_flight
                if self.paused and idle:
                    self.paused = False
                status = "now" if self.agent_ready and not self.paused and idle else "next"
                if status == "next":
                    self.last_event = f"Next dial: {name}"
        if status == "now":
            self.fill_slots()
        state = self.public_state()
        state["dial_status"] = status
        if status == "already":
            self.record_activity(f"Already dialing {name}", "web")
        else:
            self.record_activity(f"Manual dial {'placed' if status == 'now' else 'queued'} for {name}", "web")
        return state
