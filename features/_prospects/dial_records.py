"""Saved Total dials snapshots (records) separate from the live call log."""

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from features._prospects.dial_archive import archive_record_from_lead

DIAL_RECORDS_BLOB_ID = "__dial_records__"


def is_dial_records_storage_lead(lead):
    return isinstance(lead, dict) and lead.get("id") == DIAL_RECORDS_BLOB_ID


def dial_records_path(crm_path):
    path = Path(crm_path)
    if path.is_dir() or not path.suffix:
        return path / "dial_records.json"
    return path.with_name("dial_records.json")


def _default_title():
    stamp = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")
    return f"Record · {stamp}"


def collect_active_dial_records(leads, archived_records):
    """Every row currently shown on Total dials, in archive record shape."""
    rows = []
    seen = set()
    for lead in leads or []:
        log = lead.get("call_log") or []
        for entry in log:
            record = archive_record_from_lead(lead, entry)
            if record["id"] in seen:
                continue
            seen.add(record["id"])
            rows.append(record)
        if not log and lead.get("transcript"):
            stamps = sorted(line.get("timestamp") or "" for line in lead["transcript"] if line.get("timestamp"))
            stub = {"started_at": stamps[0] if stamps else "", "ended_at": stamps[-1] if stamps else ""}
            record = archive_record_from_lead(lead, stub)
            if record["id"] not in seen:
                seen.add(record["id"])
                rows.append(record)
    for record in archived_records or []:
        record_id = record.get("id")
        if record_id and record_id in seen:
            continue
        if record_id:
            seen.add(record_id)
        rows.append(dict(record))
    rows.sort(
        key=lambda item: (item.get("entry") or {}).get("ended_at")
        or (item.get("entry") or {}).get("started_at")
        or "",
        reverse=True,
    )
    return rows


def snapshot_active_dials(crm, dial_archive, records_store, title=None):
    leads = crm.snapshot()
    archived = dial_archive.snapshot()
    dial_rows = collect_active_dial_records(leads, archived)
    if not dial_rows:
        raise ValueError("There are no dials in the current record to save.")
    saved = records_store.append_record(title, dial_rows)
    crm.clear_all_call_logs()
    dial_archive.replace_all([])
    return saved


class LocalDialRecordsStore:
    def __init__(self, crm_path):
        self.path = dial_records_path(crm_path)
        self.lock = threading.RLock()
        self.saved = []
        self.revision = 0
        self.load()

    def load(self):
        with self.lock:
            try:
                if self.path.is_file():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    self.saved = data if isinstance(data, list) else []
                else:
                    self.saved = []
            except (OSError, json.JSONDecodeError):
                self.saved = []

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(self.saved, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.path)
            self.revision += 1

    def list_summaries(self):
        with self.lock:
            return [
                {
                    "id": item["id"],
                    "title": item.get("title") or "",
                    "saved_at": item.get("saved_at") or "",
                    "dial_count": len(item.get("records") or []),
                }
                for item in self.saved
            ]

    def get_record(self, record_id):
        with self.lock:
            for item in self.saved:
                if item.get("id") == record_id:
                    return {
                        "id": item["id"],
                        "title": item.get("title") or "",
                        "saved_at": item.get("saved_at") or "",
                        "dial_count": len(item.get("records") or []),
                        "records": [dict(row) for row in item.get("records") or []],
                    }
        return None

    def append_record(self, title, dial_rows):
        entry = {
            "id": str(uuid.uuid4()),
            "title": (title or "").strip() or _default_title(),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "records": [dict(row) for row in dial_rows],
        }
        with self.lock:
            self.saved.insert(0, entry)
            self.save()
        return {
            "id": entry["id"],
            "title": entry["title"],
            "saved_at": entry["saved_at"],
            "dial_count": len(entry["records"]),
        }


class SupabaseDialRecordsStore:
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

    def _blob_lead(self, saved):
        return {
            "id": DIAL_RECORDS_BLOB_ID,
            "name": "",
            "phone": "",
            "business": "",
            "status": "new",
            "timezone": "",
            "dial_saved_records": [dict(item) for item in saved],
        }

    def _fetch(self):
        rows = self.client.request(
            "GET",
            "prospects",
            self._scope({"id": f"eq.{DIAL_RECORDS_BLOB_ID}", "select": "data"}),
        )
        if not rows:
            return []
        data = rows[0].get("data") if isinstance(rows[0], dict) else {}
        stored = data.get("dial_saved_records") if isinstance(data, dict) else []
        return [dict(item) for item in stored] if isinstance(stored, list) else []

    def _all(self):
        if self._cache is None:
            self._cache = self._fetch()
        return self._cache

    def _save(self, saved):
        payload = self._blob_lead(saved)
        self.client.request(
            "POST",
            "prospects",
            {"on_conflict": "id"},
            [{"id": DIAL_RECORDS_BLOB_ID, "user_id": self.user_id, "data": payload}],
            "resolution=merge-duplicates,return=minimal",
        )

    def list_summaries(self):
        with self.lock:
            return [
                {
                    "id": item["id"],
                    "title": item.get("title") or "",
                    "saved_at": item.get("saved_at") or "",
                    "dial_count": len(item.get("records") or []),
                }
                for item in self._all()
            ]

    def get_record(self, record_id):
        with self.lock:
            for item in self._all():
                if item.get("id") == record_id:
                    return {
                        "id": item["id"],
                        "title": item.get("title") or "",
                        "saved_at": item.get("saved_at") or "",
                        "dial_count": len(item.get("records") or []),
                        "records": [dict(row) for row in item.get("records") or []],
                    }
        return None

    def append_record(self, title, dial_rows):
        entry = {
            "id": str(uuid.uuid4()),
            "title": (title or "").strip() or _default_title(),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "records": [dict(row) for row in dial_rows],
        }
        with self.lock:
            merged = list(self._all())
            merged.insert(0, entry)
            self._save(merged)
            self._cache = merged
            self._touch()
        return {
            "id": entry["id"],
            "title": entry["title"],
            "saved_at": entry["saved_at"],
            "dial_count": len(entry["records"]),
        }


def DialRecordsStore(*args, client=None, user_id=None, crm_path=None, **kwargs):
    if client is not None:
        return SupabaseDialRecordsStore(client, user_id=user_id)
    if crm_path is None and args:
        crm_path = args[0]
    return LocalDialRecordsStore(crm_path)
