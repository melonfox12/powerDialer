"""Prospect rules shared by the local and Supabase backends."""

import urllib.parse
from datetime import datetime, timedelta

from features._prospects.backend_local import LocalBackend
from features._prospects.backend_supabase import SupabaseBackend
from features._prospects.csv_export import csv_bytes_for
from features._prospects.csv_import import parse_csv
from shared.infra import utc_now
from shared.vocabulary import STATUS_KEYS


class ProspectStore:
    def __init__(self, path=None, *, client=None, user_id=None):
        if client is not None:
            self.backend = SupabaseBackend(client, user_id)
        else:
            self.backend = LocalBackend(path)

    @property
    def lock(self):
        return self.backend.lock

    @property
    def leads(self):
        return self.backend.leads

    @leads.setter
    def leads(self, value):
        self.backend.leads = value

    @property
    def revision(self):
        return self.backend.revision

    def snapshot(self):
        return self.backend.snapshot()

    def timezone_groups(self, leads=None):
        return self.backend.timezone_groups(leads)

    def csv_bytes(self):
        return self.backend.csv_bytes()

    def add_lead(self, payload):
        return self.backend.add_lead(payload)

    def add_csv(self, data):
        return self.backend.add_csv(data)

    def remove(self, lead_id):
        return self.backend.remove(lead_id)

    def save(self):
        return self.backend.save()

    def set_status(self, lead_id, status, scheduled_until=None):
        if status not in STATUS_KEYS:
            raise ValueError("Unknown prospect status")
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
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
                lead["scheduled_until"] = (utc_now() + timedelta(hours=24)).isoformat() if status == "call" else None
            self.backend.save_locked(lead)
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
            leads = self.backend.leads_locked()
            lead = next((item for item in leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            transcript = lead.setdefault("transcript", [])
            if entry["id"] and any(item.get("id") == entry["id"] for item in transcript):
                return dict(lead)
            transcript.append(entry)
            transcript.sort(key=lambda item: item.get("timestamp", ""))
            self.backend.save_locked(lead)
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
            leads = self.backend.leads_locked()
            lead = next((item for item in leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            log = lead.setdefault("call_log", [])
            if record["id"] and any(item.get("id") == record["id"] for item in log):
                return dict(lead)
            log.append(record)
            self.backend.save_locked(lead)
            return dict(lead)


def post_lead(request, data):
    lead = request.account.crm.add_lead(data)
    request.send_json(200, {"lead": lead, "state": request.ctx.state()})


def post_import(request, data):
    result = request.account.crm.add_csv(data)
    try:
        state = request.ctx.state()
    except Exception as exc:
        request.ctx.log(f"Imported CSV but could not refresh state: {exc}", "error")
        state = {"leads": request.account.crm.snapshot()}
    request.send_json(200, {"import": result, "state": state})


def get_export(request):
    try:
        content = request.account.crm.csv_bytes()
        request.send_bytes(200, content, "text/csv; charset=utf-8", {
            "Content-Disposition": "attachment; filename=crm-export.csv",
        })
    except OSError as exc:
        request.report_storage_error(exc)


def delete_lead(request):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/"))
    try:
        request.account.crm.remove(lead_id)
        request.send_json(200, request.ctx.state())
    except KeyError as exc:
        request._trace_error = str(exc)
        request.send_json(404, {"error": str(exc)})
    except OSError as exc:
        request._trace_error = str(exc)
        request.send_json(500, {"error": f"Could not persist data: {exc}"})


ROUTES = [
    ("POST", "/api/leads", post_lead, "POST"),
    ("POST", "/api/import", post_import, "POST"),
    ("GET", "/api/export.csv", get_export, "GET reads"),
    ("DELETE", "/api/leads/{id}", delete_lead, "DELETE"),
]
