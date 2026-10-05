from datetime import datetime, timedelta
from crm_store import STATUSES, parse_csv, utc_now
from crm_store.leads.manual import build_manual_lead

class ChangeMixin:
    def add_lead(self, payload):
        with self.lock:
            leads = self._all()
            self._expire(leads)
            lead = build_manual_lead(payload, (item["phone"] for item in leads))
            self.client.request(
                "POST",
                "prospects",
                {"on_conflict": "id"},
                [{"id": lead["id"], "user_id": self.user_id, "data": lead}],
                "resolution=merge-duplicates,return=minimal",
            )
            leads.append(lead)
            self._touch()
            return dict(lead)

    def add_csv(self, data):
        with self.lock:
            leads = self._all()
            self._expire(leads)
            additions, info = parse_csv(data, (lead["phone"] for lead in leads))
            if additions:
                rows = [
                    {"id": lead["id"], "user_id": self.user_id, "data": lead}
                    for lead in additions
                ]
                for start in range(0, len(rows), 500):
                    self.client.request(
                        "POST",
                        "prospects",
                        {"on_conflict": "id"},
                        rows[start:start + 500],
                        "resolution=merge-duplicates,return=minimal",
                    )
            leads.extend(additions)
            info["added"] = len(additions)
            info["total"] = len(leads) + len(additions)
            if additions:
                self._touch()
            return info

    def set_status(self, lead_id, status, scheduled_until=None):
        if status not in STATUSES:
            raise ValueError("Unknown prospect status")
        with self.lock:
            leads = self._all()
            self._expire(leads)
            lead = next((item for item in leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            lead["status"] = status
            if scheduled_until:
                try:
                    due = datetime.fromisoformat(str(scheduled_until))
                except ValueError as exc:
                    raise ValueError("Callback time must be a valid ISO datetime.") from exc
                if due.tzinfo is None:
                    raise ValueError("Callback time must include a timezone.")
                if due <= utc_now():
                    raise ValueError("Callback time must be in the future.")
                lead["scheduled_until"] = due.isoformat()
            else:
                lead["scheduled_until"] = (
                    (utc_now() + timedelta(hours=24)).isoformat() if status == "call" else None
                )
            self._write(lead)
            self._touch()
            return dict(lead)

    def remove(self, lead_id):
        with self.lock:
            rows = self.client.request(
                "DELETE",
                "prospects",
                self._scope({"id": f"eq.{lead_id}", "select": "id"}),
                prefer="return=representation",
            )
            if not rows:
                raise KeyError("Prospect not found")
            if self._cache is not None:
                self._cache = [lead for lead in self._cache if lead["id"] != lead_id]
            self._touch()
