import random
from core.dialer_session import within_calling_window

class SlotMixin:
    def fill_slots(self):
        leads = self.crm.snapshot()
        launches = []
        with self.lock:
            if not self.running or self.paused or not self.agent_ready or self.active or self.pending_outcome:
                return
            active_leads = {call["lead_id"] for call in self.in_flight.values()}
            slots = max(0, 1 - len(self.in_flight))
            manual = self._claim_manual_lead(leads, active_leads) if slots else None
            if manual:
                selected = [manual]
            else:
                pool = [
                    lead for lead in self._pool_leads(leads)
                    if lead["id"] not in active_leads
                    and within_calling_window(
                        lead.get("timezone"),
                        int(self.settings.get("CALLING_START_HOUR", "8")),
                        int(self.settings.get("CALLING_END_HOUR", "21")),
                    )
                ]
                selected = random.sample(pool, min(slots, len(pool)))
            for lead in selected:
                call = self._new_call("prospect", lead)
                call["caller_id"] = self._next_caller()
                launches.append((call, lead["phone"]))
        for call, destination in launches:
            self._launch_call(call, destination)
        self._schedule_calling_window_check()
