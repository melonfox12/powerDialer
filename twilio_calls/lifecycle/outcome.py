from core.dialer_session import record_disposition, status_for_disposition
from shared.vocabulary import DEFAULT_OUTCOME_METRIC, OUTCOME_METRIC

class OutcomeMixin:
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
        metric_key = OUTCOME_METRIC.get(status, DEFAULT_OUTCOME_METRIC)
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
