"""Supabase REST persistence for CRM records and dialer metrics."""

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from crm_store import STATUSES, csv_bytes_for, parse_csv, utc_now
from twilio_calls import DIALER_DEFAULTS

METRIC_KEYS = {
    "booked", "call_later", "connected", "disqualified", "interested", "dials",
    "failed", "talk_seconds", "voicemail",
}
SETTINGS_ROW_ID = "app"
REMOTE_SETTING_KEYS = (
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
    "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
    *DIALER_DEFAULTS.keys(),
)


class SupabaseClient:
    def __init__(self, url, service_key, timeout=20, anon_key=""):
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("SUPABASE_URL must be an HTTPS project URL.")
        if not service_key:
            raise ValueError("Set SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY in .env.")
        if service_key.startswith(("sb_publishable_", "sb_anon_")):
            raise ValueError(
                "A publishable/anon Supabase key cannot access server-side storage. "
                "Use a Supabase secret key or legacy service_role key."
            )
        if service_key.count(".") == 2:
            try:
                payload = service_key.split(".")[1]
                claims = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
            except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError("The Supabase server key is invalid.") from exc
            if not isinstance(claims, dict) or claims.get("role") != "service_role":
                raise ValueError(
                    "The Supabase JWT must have the service_role role for server-side storage."
                )
        self.project_url = url.rstrip("/")
        self.base_url = self.project_url + "/rest/v1/"
        self.service_key = service_key
        self.anon_key = (anon_key or "").strip()
        self.timeout = timeout

    @classmethod
    def from_env(cls, values):
        url = values.get("SUPABASE_URL", "").strip()
        key = (
            values.get("SUPABASE_SECRET_KEY", "").strip()
            or values.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
        )
        anon = (
            values.get("SUPABASE_ANON_KEY", "").strip()
            or values.get("SUPABASE_PUBLISHABLE_KEY", "").strip()
        )
        if bool(url) != bool(key):
            raise ValueError(
                "Configure both SUPABASE_URL and SUPABASE_SECRET_KEY "
                "(or SUPABASE_SERVICE_ROLE_KEY), or remove both to use local JSON storage."
            )
        return cls(url, key, anon_key=anon) if url else None

    def auth_user(self, access_token):
        token = (access_token or "").strip()
        if not token:
            return None
        url = self.project_url + "/auth/v1/user"
        request = urllib.request.Request(url, method="GET")
        request.add_header("apikey", self.anon_key or self.service_key)
        request.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return None
            raise OSError(f"Supabase auth HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"Could not reach Supabase auth: {exc.reason}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSError("Supabase auth returned an invalid JSON response.") from exc
        user_id = payload.get("id") if isinstance(payload, dict) else None
        if not user_id:
            return None
        return {
            "id": str(user_id),
            "email": str(payload.get("email") or ""),
        }

    def request(self, method, resource, params=None, payload=None, prefer=None):
        url = self.base_url + resource
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("apikey", self.service_key)
        request.add_header("Authorization", f"Bearer {self.service_key}")
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        if prefer:
            request.add_header("Prefer", prefer)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = response.read()
        except urllib.error.HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                if not isinstance(error_body, dict):
                    raise ValueError("Unexpected error response")
                message = error_body.get("message", "Supabase request failed")
            except (ValueError, OSError):
                message = "Supabase request failed"
            raise OSError(f"Supabase HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise OSError(f"Could not reach Supabase: {exc.reason}") from exc
        if not result:
            return None
        try:
            return json.loads(result.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OSError("Supabase returned an invalid JSON response.") from exc

    def select_all(self, resource, params=None, page_size=500):
        rows = []
        offset = 0
        while True:
            page_params = dict(params or {})
            page_params.update({"limit": str(page_size), "offset": str(offset)})
            page = self.request("GET", resource, page_params)
            if not isinstance(page, list):
                raise OSError(f"Supabase returned an invalid {resource} response.")
            rows.extend(page)
            if len(page) < page_size:
                return rows
            offset += page_size


class SupabaseCRMStore:
    def __init__(self, client, user_id=None):
        self.client = client
        self.user_id = user_id
        self.lock = threading.RLock()

    def _scope(self, params=None):
        scoped = dict(params or {})
        if self.user_id:
            scoped["user_id"] = f"eq.{self.user_id}"
        return scoped

    def _all(self):
        rows = self.client.select_all("prospects", self._scope({"select": "id,data", "order": "id"}))
        leads = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("data"), dict):
                raise OSError("Supabase contains an invalid prospect record.")
            if row["data"].get("id") != row.get("id"):
                raise OSError("A Supabase prospect id does not match its stored record.")
            leads.append(row["data"])
        return leads

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
            info["added"] = len(additions)
            info["total"] = len(leads) + len(additions)
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
            return dict(lead)

    def append_transcript(self, lead_id, segment):
        entry = {
            "id": str(segment.get("id", "")),
            "timestamp": str(segment.get("timestamp", "")),
            "speaker": str(segment.get("speaker", "")),
            "text": str(segment.get("text", "")).strip(),
        }
        if not entry["text"] or entry["speaker"] not in ("Agent", "Prospect"):
            raise ValueError("A transcript segment needs text and a known speaker.")
        with self.lock:
            leads = self._all()
            lead = next((item for item in leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            transcript = lead.setdefault("transcript", [])
            if entry["id"] and any(item.get("id") == entry["id"] for item in transcript):
                return dict(lead)
            transcript.append(entry)
            transcript.sort(key=lambda item: item.get("timestamp", ""))
            self._write(lead)
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

    def snapshot(self):
        with self.lock:
            leads = self._all()
            self._expire(leads)
            return leads

    def timezone_groups(self):
        counts = {}
        for lead in self.snapshot():
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


def migrate_local_data(client, crm_path, metrics_path):
    """Import local JSON data without overwriting different remote records."""
    from crm_store import CRMStore
    from metrics_store import MetricsStore

    prospects = CRMStore(crm_path).leads
    metric_data = MetricsStore(metrics_path).data
    local_prospects = {lead["id"]: lead for lead in prospects}
    local_daily = {
        (day, key): value
        for day, values in metric_data.get("daily", {}).items()
        for key, value in values.items()
    }
    local_totals = metric_data.get("all_time", {})

    existing_prospects = client.select_all("prospects", {"select": "id,data"})
    existing_daily = client.select_all(
        "dialer_metric_daily", {"select": "day,metric_key,value"}
    )
    existing_totals = client.select_all(
        "dialer_metric_totals", {"select": "metric_key,value"}
    )
    existing_sessions = client.select_all("dialer_sessions", {"select": "id,data"})
    for row in existing_prospects:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid prospect record.")
        if local_prospects.get(row.get("id")) != row.get("data"):
            raise ValueError("Migration stopped: Supabase contains prospect data that differs from local data.")
    for row in existing_daily:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid daily metric.")
        if local_daily.get((str(row.get("day")), row.get("metric_key"))) != row.get("value"):
            raise ValueError("Migration stopped: Supabase contains daily metrics that differ from local data.")
    for row in existing_totals:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid all-time metric.")
        if local_totals.get(row.get("metric_key")) != row.get("value"):
            raise ValueError("Migration stopped: Supabase contains all-time metrics that differ from local data.")
    local_sessions = {
        session["id"]: session for session in metric_data.get("sessions", [])
        if isinstance(session, dict) and session.get("id")
    }
    for row in existing_sessions:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid session.")
        if local_sessions.get(row.get("id")) != row.get("data"):
            raise ValueError("Migration stopped: Supabase contains session data that differs from local data.")
    for start in range(0, len(prospects), 500):
        batch = prospects[start:start + 500]
        client.request(
            "POST",
            "prospects",
            {"on_conflict": "id"},
            [{"id": lead["id"], "data": lead} for lead in batch],
            "resolution=merge-duplicates,return=minimal",
        )
    daily_rows = [
        {"day": day, "metric_key": key, "value": value}
        for day, values in metric_data.get("daily", {}).items()
        for key, value in values.items()
        if value
    ]
    total_rows = [
        {"metric_key": key, "value": value}
        for key, value in metric_data.get("all_time", {}).items()
        if value
    ]
    for table, rows in (
        ("dialer_metric_daily", daily_rows),
        ("dialer_metric_totals", total_rows),
    ):
        for start in range(0, len(rows), 500):
            client.request(
                "POST", table, payload=rows[start:start + 500],
                prefer="resolution=merge-duplicates,return=minimal",
            )
    sessions = list(local_sessions.values())
    for start in range(0, len(sessions), 500):
        client.request(
            "POST",
            "dialer_sessions",
            payload=[{
                "id": session["id"],
                "started_at": session["started_at"],
                "ended_at": session.get("ended_at"),
                "data": session,
            } for session in sessions[start:start + 500]],
            prefer="resolution=merge-duplicates,return=minimal",
        )
    return {"prospects": len(prospects), "daily_metrics": len(daily_rows), "totals": len(total_rows)}


def load_app_settings(client, user_id=None):
    row_id = str(user_id or SETTINGS_ROW_ID)
    try:
        rows = client.request(
            "GET",
            "dialer_settings",
            {"id": f"eq.{row_id}", "select": "data"},
        )
    except OSError as exc:
        if "HTTP 404" in str(exc) or "PGRST205" in str(exc) or "does not exist" in str(exc).lower():
            return {}
        raise
    if not rows:
        return {}
    if not isinstance(rows, list) or not isinstance(rows[0], dict) or not isinstance(rows[0].get("data"), dict):
        raise OSError("Supabase returned invalid dialer settings.")
    stored = rows[0]["data"]
    return {
        key: str(stored[key])
        for key in REMOTE_SETTING_KEYS
        if stored.get(key) not in (None, "")
    }


def save_app_settings(client, values, user_id=None):
    payload = {
        "id": str(user_id or SETTINGS_ROW_ID),
        "data": {key: str(values.get(key, "") or "") for key in REMOTE_SETTING_KEYS},
    }
    client.request(
        "POST",
        "dialer_settings",
        {"on_conflict": "id"},
        [payload],
        "resolution=merge-duplicates,return=minimal",
    )


def hydrate_env_from_supabase(env_path, client):
    from twilio_calls import read_env, write_env

    remote = load_app_settings(client)
    if not remote:
        return False
    local = read_env(env_path)
    updates = {
        key: value for key, value in remote.items()
        if value and not str(local.get(key, "")).strip()
    }
    if updates:
        write_env(env_path, updates)
        return True
    return False
