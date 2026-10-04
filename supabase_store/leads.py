"""Supabase REST persistence for CRM records and dialer metrics."""

import base64
import http.client
import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

from crm_store import STATUSES, csv_bytes_for, parse_csv, utc_now
from twilio_calls.settings import DIALER_DEFAULTS

from supabase_store.transcripts import TranscriptMixin

class SupabaseCRMStore(TranscriptMixin):
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

    def snapshot(self):
        with self.lock:
            leads = self._all()
            self._expire(leads)
            return leads

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


class SupabaseMetricsStore:
    def __init__(self, client, user_id=None):
        self.client = client
        self.user_id = user_id
        self._cached_snapshot = None
        self._cached_at = 0

    def _scope(self, params=None):
        scoped = dict(params or {})
        if self.user_id:
            scoped["user_id"] = f"eq.{self.user_id}"
        return scoped

    def bump(self, key, amount=1):
        if key not in METRIC_KEYS:
            raise ValueError(f"Unknown dialer metric: {key}")
        if not isinstance(amount, int) or amount <= 0:
            raise ValueError("Metric increments must be positive integers.")
        if not self.user_id:
            raise ValueError("Sign in to record dialer metrics.")
        self._cached_snapshot = None
        self.client.request(
            "POST",
            "rpc/increment_dialer_metric",
            payload={"metric_key": key, "increment_by": amount, "for_user": self.user_id},
        )

    def save_session(self, session):
        self.client.request(
            "POST",
            "dialer_sessions",
            {"on_conflict": "id"},
            {
                "id": session["id"],
                "user_id": self.user_id,
                "started_at": session["started_at"],
                "ended_at": session.get("ended_at"),
                "data": session,
            },
            "resolution=merge-duplicates,return=minimal",
        )

    def recent_sessions(self, limit=5):
        rows = self.client.request(
            "GET",
            "dialer_sessions",
            self._scope({"select": "data", "order": "started_at.desc", "limit": str(limit)}),
        )
        if not isinstance(rows, list) or any(not isinstance(row.get("data"), dict) for row in rows):
            raise OSError("Supabase returned an invalid session history response.")
        return [row["data"] for row in rows]

    def snapshot(self, days=7):
        if self._cached_snapshot is not None and time.time() - self._cached_at < 10:
            return self._cached_snapshot
        result = self._load_snapshot(days)
        self._cached_snapshot = result
        self._cached_at = time.time()
        return result

    def _load_snapshot(self, days=7):
        today = utc_now().date()
        start = today - timedelta(days=days - 1)
        daily_rows = self.client.request(
            "GET",
            "dialer_metric_daily",
            self._scope({
                "select": "day,metric_key,value",
                "day": f"gte.{start.isoformat()}",
                "order": "day",
            }),
        )
        total_rows = self.client.request(
            "GET",
            "dialer_metric_totals",
            self._scope({"select": "metric_key,value"}),
        )
        if not isinstance(daily_rows, list) or not isinstance(total_rows, list):
            raise OSError("Supabase returned an invalid metrics response.")
        today_metrics = {}
        by_day = {}
        for row in daily_rows:
            if not isinstance(row, dict):
                raise OSError("Supabase contains an invalid daily metric.")
            try:
                day = str(row["day"])
                key = str(row["metric_key"])
                value = int(row["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise OSError("Supabase contains an invalid daily metric.") from exc
            by_day.setdefault(day, {})[key] = value
            if day == today.isoformat():
                today_metrics[key] = value
        all_time = {}
        for row in total_rows:
            if not isinstance(row, dict):
                raise OSError("Supabase contains an invalid all-time metric.")
            try:
                all_time[str(row["metric_key"])] = int(row["value"])
            except (KeyError, TypeError, ValueError) as exc:
                raise OSError("Supabase contains an invalid all-time metric.") from exc
        series = []
        for offset in range(days - 1, -1, -1):
            day = (today - timedelta(days=offset)).isoformat()
            metrics = by_day.get(day, {})
            series.append({
                "date": day,
                "dials": metrics.get("dials", 0),
                "connected": metrics.get("connected", 0),
                "booked": metrics.get("booked", 0),
            })
        return {"today": today_metrics, "all_time": all_time, "daily": series}
