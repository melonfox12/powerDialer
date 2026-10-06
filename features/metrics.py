"""Local JSON and Supabase dialing metrics."""

import json
import threading
import time
from datetime import timedelta
from pathlib import Path

from shared.infra import utc_now
from shared.vocabulary import METRIC_KEYS


class MetricsStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = {"daily": {}, "all_time": {}}
        self.load()

    def load(self):
        with self.lock:
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    if isinstance(data, dict):
                        self.data = data
                except (OSError, json.JSONDecodeError):
                    pass
            self.data.setdefault("daily", {})
            self.data.setdefault("all_time", {})
            self.data.setdefault("sessions", [])

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temp_path.write_text(json.dumps(self.data, indent=2), encoding="utf-8")
            temp_path.replace(self.path)

    @staticmethod
    def _today():
        return utc_now().strftime("%Y-%m-%d")

    def bump(self, key, amount=1):
        with self.lock:
            bucket = self.data["daily"].setdefault(self._today(), {})
            bucket[key] = bucket.get(key, 0) + amount
            self.data["all_time"][key] = self.data["all_time"].get(key, 0) + amount
            self.save()

    def save_session(self, session):
        with self.lock:
            sessions = self.data.setdefault("sessions", [])
            for index, stored in enumerate(sessions):
                if stored.get("id") == session.get("id"):
                    sessions[index] = dict(session)
                    break
            else:
                sessions.append(dict(session))
            self.data["sessions"] = sessions[-100:]
            self.save()

    def recent_sessions(self, limit=5):
        with self.lock:
            return [dict(session) for session in reversed(self.data.get("sessions", [])[-limit:])]

    def snapshot(self, days=7):
        with self.lock:
            today = dict(self.data["daily"].get(self._today(), {}))
            all_time = dict(self.data["all_time"])
            series = []
            now = utc_now()
            for offset in range(days - 1, -1, -1):
                day = (now - timedelta(days=offset)).strftime("%Y-%m-%d")
                bucket = self.data["daily"].get(day, {})
                series.append({
                    "date": day,
                    "dials": bucket.get("dials", 0),
                    "connected": bucket.get("connected", 0),
                    "booked": bucket.get("booked", 0),
                })
            return {"today": today, "all_time": all_time, "daily": series}


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
        today = utc_now().date().isoformat()
        self._increment("dialer_metric_daily", {"user_id": self.user_id, "day": today, "metric_key": key}, amount, "user_id,day,metric_key")
        self._increment("dialer_metric_totals", {"user_id": self.user_id, "metric_key": key}, amount, "user_id,metric_key")

    def _increment(self, resource, identity, amount, conflict):
        filters = {key: f"eq.{value}" for key, value in identity.items()}
        filters["select"] = "value"
        rows = self.client.request("GET", resource, filters)
        current = int(rows[0]["value"]) if rows else 0
        self.client.request(
            "POST",
            resource,
            {"on_conflict": conflict},
            {**identity, "value": current + amount},
            "resolution=merge-duplicates,return=minimal",
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


def get_metrics(request):
    try:
        request.send_json(200, request.account.metrics.snapshot())
    except OSError as exc:
        request.report_storage_error(exc)


ROUTES = [
    ("GET", "/api/metrics", get_metrics, "GET reads"),
]
