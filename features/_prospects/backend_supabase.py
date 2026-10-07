"""Supabase prospect persistence. Rules live in features.prospects."""

import threading
from datetime import datetime

from features._prospects.csv_export import csv_bytes_for
from features._prospects.csv_import import build_manual_lead, parse_csv
from shared.infra import utc_now

class SupabaseBackend:
    def __init__(self, client, user_id=None):
        self.client = client
        self.user_id = user_id
        self.lock = threading.RLock()
        self._cache = None
        self.revision = 0

    def _scope(self, params=None):
        scoped = dict(params or {})
        if self.user_id:
            scoped["user_id"] = f"eq.{self.user_id}"
        return scoped

    def _touch(self):
        self.revision += 1

    def _fetch(self):
        rows = self.client.select_all("prospects", self._scope({"select": "id,data", "order": "id"}))
        leads = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("data"), dict):
                raise OSError("Supabase contains an invalid prospect record.")
            if row["data"].get("id") != row.get("id"):
                raise OSError("A Supabase prospect id does not match its stored record.")
            leads.append(row["data"])
        return leads

    def _all(self):
        if self._cache is None:
            self._cache = self._fetch()
        return self._cache

    def _write(self, lead):
        rows = self.client.request(
            "PATCH",
            "prospects",
            self._scope({"id": f"eq.{lead['id']}"}),
            {"data": lead, "user_id": self.user_id},
            "return=representation",
        )
        if not rows:
            raise KeyError("Prospect not found")

    def _expire(self, leads):
        now = utc_now()
        for lead in leads:
            deadline = lead.get("scheduled_until")
            if lead.get("status") == "call" and deadline:
                try:
                    due = datetime.fromisoformat(deadline)
                except ValueError:
                    due = now
                if due <= now:
                    lead["status"] = "new"
                    lead["scheduled_until"] = None
                    self._write(lead)
                    self._touch()

    def snapshot(self):
        with self.lock:
            leads = self._all()
            self._expire(leads)
            return [dict(lead) for lead in leads]

    def timezone_groups(self, leads=None):
        counts = {}
        for lead in self.snapshot() if leads is None else leads:
            if lead.get("status") != "new":
                continue
            timezone = lead.get("timezone") or "Unknown"
            counts[timezone] = counts.get(timezone, 0) + 1
        return sorted(counts.items(), key=lambda item: (item[0] == "Unknown", -item[1], item[0]))

    def csv_bytes(self):
        return csv_bytes_for(self.snapshot())
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
            info["total"] = len(leads)
            if additions:
                self._touch()
            return info


    def leads_locked(self):
        return self._all()

    def expire_locked(self, leads):
        self._expire(leads)

    def save_locked(self, lead):
        self._write(lead)
        leads = self._all()
        for index, item in enumerate(leads):
            if item["id"] == lead["id"]:
                leads[index] = lead
        self._touch()

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
