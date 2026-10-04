"""Persistent CRM records and flexible CSV import/export."""

import csv
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

from crm_store.csv_io import csv_bytes_for, parse_csv
from crm_store.statuses import STATUSES, utc_now

class CRMStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.leads = []
        self.revision = 0
        self.load()

    def load(self):
        with self.lock:
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    self.leads = data if isinstance(data, list) else []
                except (OSError, json.JSONDecodeError):
                    self.leads = []
            self.expire_due(save=False)

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temp_path.write_text(json.dumps(self.leads, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self.path)
            self.revision += 1

    def expire_due(self, save=True):
        now = utc_now()
        changed = False
        with self.lock:
            for lead in self.leads:
                deadline = lead.get("scheduled_until")
                if lead.get("status") == "call" and deadline:
                    try:
                        due = datetime.fromisoformat(deadline)
                    except ValueError:
                        due = now
                    if due <= now:
                        lead["status"] = "new"
                        lead["scheduled_until"] = None
                        changed = True
            if changed and save:
                self.save()
        return changed

    def add_csv(self, data):
        with self.lock:
            self.expire_due(save=False)
            leads, info = parse_csv(data, (lead["phone"] for lead in self.leads))
            self.leads.extend(leads)
            self.save()
            info["added"] = len(leads)
            info["total"] = len(self.leads)
            return info

    def set_status(self, lead_id, status, scheduled_until=None):
        if status not in STATUSES:
            raise ValueError("Unknown prospect status")
        with self.lock:
            self.expire_due(save=False)
            lead = next((item for item in self.leads if item["id"] == lead_id), None)
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
            self.save()
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
            lead = next((item for item in self.leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            transcript = lead.setdefault("transcript", [])
            if entry["id"] and any(item.get("id") == entry["id"] for item in transcript):
                return dict(lead)
            transcript.append(entry)
            transcript.sort(key=lambda item: item.get("timestamp", ""))
            self.save()
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
            lead = next((item for item in self.leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            log = lead.setdefault("call_log", [])
            if record["id"] and any(item.get("id") == record["id"] for item in log):
                return dict(lead)
            log.append(record)
            self.save()
            return dict(lead)

    def remove(self, lead_id):
        with self.lock:
            original_count = len(self.leads)
            self.leads = [lead for lead in self.leads if lead["id"] != lead_id]
            if len(self.leads) == original_count:
                raise KeyError("Prospect not found")
            self.save()

    def snapshot(self):
        self.expire_due()
        with self.lock:
            return [dict(lead) for lead in self.leads]

    def timezone_groups(self, leads=None):
        counts = {}
        for lead in self.snapshot() if leads is None else leads:
            if lead["status"] != "new":
                continue
            tz = lead.get("timezone") or "Unknown"
            counts[tz] = counts.get(tz, 0) + 1
        return sorted(counts.items(), key=lambda item: (item[0] == "Unknown", -item[1], item[0]))

    def csv_bytes(self):
        return csv_bytes_for(self.snapshot())

