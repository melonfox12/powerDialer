"""Supabase REST persistence for CRM records and dialer metrics."""

import base64
import http.client
import json
import threading
import time
import urllib.parse
from datetime import datetime, timedelta

from crm_store import STATUSES, csv_bytes_for, parse_csv, utc_now
from supabase_store.client import REMOTE_SETTING_KEYS, SETTINGS_ROW_ID
from twilio_calls.settings import DIALER_DEFAULTS

class TranscriptMixin:

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
            self._touch()
            return dict(lead)

    def append_call_log(self, lead_id, entry):
        record = {
            "id": str(entry.get("id") or ""),
            "started_at": str(entry.get("started_at") or ""),
            "ended_at": str(entry.get("ended_at") or ""),
            "caller_id": str(entry.get("caller_id") or ""),
            "answered_by": str(entry.get("answered_by") or ""),
            "duration_seconds": int(entry.get("duration_seconds") or 0),
            "transcript_lines": int(entry.get("transcript_lines") or 0),
        }
        with self.lock:
            leads = self._all()
            lead = next((item for item in leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            log = lead.setdefault("call_log", [])
            if record["id"] and any(item.get("id") == record["id"] for item in log):
                return dict(lead)
            log.append(record)
            self._write(lead)
            self._touch()
            return dict(lead)

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
