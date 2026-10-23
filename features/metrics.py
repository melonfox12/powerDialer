"""Local JSON and Supabase dialing metrics."""

import json
import threading
import time
import urllib.parse
from datetime import timedelta
from pathlib import Path

from features import performance, settings
from shared.infra import debug_event, utc_now
from shared.vocabulary import DEFAULT_PERFORMANCE_RANGE, METRIC_KEYS


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
        day = utc_now().date().isoformat()
        try:
            self.client.request("POST", "rpc/increment_metric", payload={
                "p_user_id": self.user_id,
                "p_day": day,
                "p_metric_key": key,
                "p_amount": amount,
            })
        except OSError as exc:
            if "increment_metric" not in str(exc):
                raise
            try:
                self._increment_rows(key, amount, day)
            except OSError as row_error:
                debug_event("error", f"Could not save dial metric {key}: {row_error}")

    def _increment_rows(self, key, amount, day):
        self._add_metric("dialer_metric_daily", key, amount, day)
        self._add_metric("dialer_metric_totals", key, amount, None)

    def _add_metric(self, table, key, amount, day):
        params = {
            "select": "value",
            "user_id": f"eq.{self.user_id}",
            "metric_key": f"eq.{key}",
        }
        if day:
            params["day"] = f"eq.{day}"
        rows = self.client.request("GET", table, params) or []
        current = int(rows[0].get("value") or 0) if rows else 0
        body = {"user_id": self.user_id, "metric_key": key, "value": current + amount}
        conflict = "user_id,metric_key"
        if day:
            body["day"] = day
            conflict = "user_id,day,metric_key"
        self.client.request(
            "POST",
            table,
            {"on_conflict": conflict},
            body,
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


def get_performance(request):
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.path).query)
    range_key = (query.get("range") or [DEFAULT_PERFORMANCE_RANGE])[-1]
    dialer = request.account.dialer
    sessions = request.account.metrics.recent_sessions(100)
    with dialer.lock:
        live = dict(dialer.session) if dialer.session and dialer.running else None
    if live:
        sessions = [item for item in sessions if item.get("id") != live.get("id")] + [live]
    try:
        payload = performance.build_performance(
            request.account.crm.snapshot(),
            sessions,
            settings.daily_goal(dialer.read_settings()),
            range_key,
            (query.get("tz") or [""])[-1],
            utc_now(),
            live.get("id") if live else None,
        )
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})
        return
    request.send_json(200, payload)


def post_goal(request, data):
    goal = request.account.dialer.save_goal(data)
    request.send_json(200, {"goal": goal})


def post_booking(request, data):
    dialer = request.account.dialer
    lead = dialer.log_booking(str(data.get("lead_id") or ""), data.get("booked_at"))
    request.send_json(200, {"lead": lead, "state": dialer.public_state()})


ROUTES = [
    ("GET", "/api/metrics", get_metrics, "GET reads"),
    ("GET", "/api/performance", get_performance, "GET reads"),
    ("POST", "/api/performance/goal", post_goal, "POST"),
    ("POST", "/api/bookings", post_booking, "POST"),
]
