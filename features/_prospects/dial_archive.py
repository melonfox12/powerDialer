"""Persist Total dials rows after CRM deletes and restore them from CSV."""

import csv
import json
import re
import threading
import uuid
from io import StringIO
from pathlib import Path

from features._prospects.dials_csv_export import DIALS_CSV_HEADERS
from shared.vocabulary import CALL_OUTCOME_KEYS, canonical_status

DIAL_ARCHIVE_BLOB_ID = "__dial_archive__"


def is_dial_archive_storage_lead(lead):
    return isinstance(lead, dict) and lead.get("id") == DIAL_ARCHIVE_BLOB_ID


def dial_archive_path(crm_path):
    path = Path(crm_path)
    if path.is_dir() or not path.suffix:
        return path / "dial_archive.json"
    return path.with_name("dial_archive.json")


def _record_id(lead_id, entry):
    dial_id = str((entry or {}).get("id") or "").strip()
    if lead_id and dial_id:
        return f"{lead_id}:{dial_id}"
    started = str((entry or {}).get("started_at") or (entry or {}).get("ended_at") or "").strip()
    if lead_id and started:
        return f"{lead_id}:{started}"
    return str(uuid.uuid4())


def _normalize_entry(entry):
    item = entry or {}
    connected = item.get("connected")
    if connected not in (True, False):
        connected = None
    outcome = item.get("outcome") if item.get("outcome") in CALL_OUTCOME_KEYS else None
    duration = item.get("duration_seconds")
    transcript_lines = item.get("transcript_lines")
    return {
        "id": str(item.get("id") or ""),
        "started_at": str(item.get("started_at") or ""),
        "ended_at": str(item.get("ended_at") or ""),
        "caller_id": str(item.get("caller_id") or ""),
        "answered_by": str(item.get("answered_by") or ""),
        "duration_seconds": int(duration) if duration not in (None, "") else 0,
        "transcript_lines": int(transcript_lines) if transcript_lines not in (None, "") else 0,
        "connected": connected,
        "outcome": outcome,
    }


def archive_record_from_lead(lead, entry):
    lead_id = lead.get("id") or ""
    normalized = _normalize_entry(entry)
    return {
        "id": _record_id(lead_id, normalized),
        "lead_id": lead_id,
        "name": lead.get("name") or "",
        "phone": lead.get("phone") or "",
        "business": lead.get("business") or "",
        "review_count": lead.get("review_count"),
        "timezone": lead.get("timezone") or "",
        "status": canonical_status(lead.get("status", "new")),
        "transcript": [dict(item) for item in (lead.get("transcript") or [])],
        "entry": normalized,
    }


def _parse_transcript_cell(text, fallback_timestamp=""):
    segments = []
    for line in (text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        match = re.match(r"^(Agent|Prospect|Speaker)\s+(.+?):\s*(.*)$", stripped)
        if not match:
            continue
        speaker = match.group(1)
        if speaker == "Speaker":
            speaker = "Agent"
        segments.append({
            "id": "",
            "timestamp": fallback_timestamp,
            "speaker": speaker,
            "text": match.group(3),
        })
    return segments


def _connected_from_csv(value):
    if value == "true":
        return True
    if value == "false":
        return False
    return None


def _entry_from_csv_row(row):
    duration = row.get("duration_seconds")
    transcript_lines = row.get("dial_transcript_lines")
    outcome = row.get("outcome") or None
    if outcome and outcome not in CALL_OUTCOME_KEYS:
        outcome = None
    return _normalize_entry({
        "id": row.get("dial_id") or "",
        "started_at": row.get("started_at") or row.get("When") or "",
        "ended_at": row.get("ended_at") or "",
        "caller_id": row.get("caller_id") or "",
        "answered_by": row.get("answered_by") or "",
        "duration_seconds": duration,
        "transcript_lines": transcript_lines,
        "connected": _connected_from_csv(row.get("connected")),
        "outcome": outcome,
    })


def archive_record_from_csv_row(row):
    lead_id = str(row.get("lead_id") or "").strip() or f"import-{uuid.uuid4()}"
    entry = _entry_from_csv_row(row)
    reviews = row.get("Reviews")
    review_count = int(reviews) if reviews not in (None, "") else None
    transcript = _parse_transcript_cell(row.get("Call transcript") or "", entry.get("started_at") or "")
    return {
        "id": _record_id(lead_id, entry),
        "lead_id": lead_id,
        "name": row.get("Prospect") or "",
        "phone": row.get("Phone") or "",
        "business": row.get("Business") or "",
        "review_count": review_count,
        "timezone": row.get("timezone") or "",
        "status": canonical_status(row.get("Status") or "new"),
        "transcript": transcript,
        "entry": entry,
    }


def pseudo_lead_from_archive(record):
    return {
        "id": record.get("lead_id") or "",
        "name": record.get("name") or "",
        "phone": record.get("phone") or "",
        "business": record.get("business") or "",
        "review_count": record.get("review_count"),
        "timezone": record.get("timezone") or "",
        "status": record.get("status") or "new",
        "transcript": record.get("transcript") or [],
        "call_log": [dict(record.get("entry") or {})],
        "crm_deleted": True,
    }


class LocalDialArchiveStore:
    def __init__(self, crm_path):
        self.path = dial_archive_path(crm_path)
        self.lock = threading.RLock()
        self.records = []
        self.revision = 0
        self.load()

    def load(self):
        with self.lock:
            try:
                if self.path.is_file():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    self.records = data if isinstance(data, list) else []
                else:
                    self.records = []
            except (OSError, json.JSONDecodeError):
                self.records = []

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(".json.tmp")
            temp_path.write_text(json.dumps(self.records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            temp_path.replace(self.path)
            self.revision += 1

    def snapshot(self):
        with self.lock:
            return [dict(item) for item in self.records]

    def upsert_many(self, records):
        if not records:
            return 0
        added = 0
        with self.lock:
            by_id = {item["id"]: item for item in self.records}
            for record in records:
                if record["id"] in by_id:
                    continue
                by_id[record["id"]] = dict(record)
                added += 1
            self.records = list(by_id.values())
            if added:
                self.save()
        return added

    def archive_lead(self, lead):
        records = []
        log = lead.get("call_log") or []
        for entry in log:
            records.append(archive_record_from_lead(lead, entry))
        if not log and lead.get("transcript"):
            stamps = sorted(line.get("timestamp") or "" for line in lead["transcript"] if line.get("timestamp"))
            stub = {"started_at": stamps[0] if stamps else "", "ended_at": stamps[-1] if stamps else ""}
            records.append(archive_record_from_lead(lead, stub))
        return self.upsert_many(records)

    def import_csv_bytes(self, data, crm=None):
        return _import_csv_bytes(self, data, crm=crm)


class SupabaseDialArchiveStore:
    def __init__(self, client, user_id=None):
        self.client = client
        self.user_id = user_id
        self.lock = threading.RLock()
        self._cache = None
        self.revision = 0
        self._use_blob = None

    def _scope(self, params=None):
        scoped = dict(params or {})
        if self.user_id:
            scoped["user_id"] = f"eq.{self.user_id}"
        return scoped

    def _touch(self):
        self.revision += 1

    def _table_missing(self, exc):
        message = str(exc).lower()
        return "dial_archive" in message and ("404" in message or "does not exist" in message or "pgrst205" in message)

    def _blob_lead(self, records):
        return {
            "id": DIAL_ARCHIVE_BLOB_ID,
            "name": "",
            "phone": "",
            "business": "",
            "status": "new",
            "timezone": "",
            "dial_archive_records": [dict(item) for item in records],
        }

    def _fetch_table(self):
        rows = self.client.select_all("dial_archive", self._scope({"select": "id,data", "order": "id"}))
        records = []
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("data"), dict):
                records.append(row["data"])
        return records

    def _fetch_blob(self):
        rows = self.client.request(
            "GET",
            "prospects",
            self._scope({"id": f"eq.{DIAL_ARCHIVE_BLOB_ID}", "select": "data"}),
        )
        if not rows:
            return []
        data = rows[0].get("data") if isinstance(rows[0], dict) else {}
        stored = data.get("dial_archive_records") if isinstance(data, dict) else []
        return [dict(item) for item in stored] if isinstance(stored, list) else []

    def _fetch(self):
        if self._use_blob:
            return self._fetch_blob()
        try:
            records = self._fetch_table()
            self._use_blob = False
            return records
        except OSError as exc:
            if not self._table_missing(exc):
                raise
            self._use_blob = True
            return self._fetch_blob()

    def _save_blob(self, records):
        payload = self._blob_lead(records)
        self.client.request(
            "POST",
            "prospects",
            {"on_conflict": "id"},
            [{"id": DIAL_ARCHIVE_BLOB_ID, "user_id": self.user_id, "data": payload}],
            "resolution=merge-duplicates,return=minimal",
        )

    def _all(self):
        if self._cache is None:
            self._cache = self._fetch()
        return self._cache

    def snapshot(self):
        with self.lock:
            return [dict(item) for item in self._all()]

    def upsert_many(self, records):
        if not records:
            return 0
        with self.lock:
            existing = {item["id"] for item in self._all()}
            additions = [dict(item) for item in records if item["id"] not in existing]
            if not additions:
                return 0
            if self._use_blob:
                merged = list(self._all())
                merged.extend(additions)
                self._save_blob(merged)
                self._cache = merged
                self._touch()
                return len(additions)
            rows = [
                {"id": item["id"], "user_id": self.user_id, "data": item}
                for item in additions
            ]
            try:
                for start in range(0, len(rows), 500):
                    self.client.request(
                        "POST",
                        "dial_archive",
                        {"on_conflict": "id"},
                        rows[start:start + 500],
                        "resolution=merge-duplicates,return=minimal",
                    )
            except OSError as exc:
                if not self._table_missing(exc):
                    raise
                self._use_blob = True
                self._cache = None
                return self.upsert_many(additions)
            self._cache = None
            self._use_blob = False
            self._touch()
            return len(additions)

    def archive_lead(self, lead):
        records = []
        log = lead.get("call_log") or []
        for entry in log:
            records.append(archive_record_from_lead(lead, entry))
        if not log and lead.get("transcript"):
            stamps = sorted(line.get("timestamp") or "" for line in lead["transcript"] if line.get("timestamp"))
            stub = {"started_at": stamps[0] if stamps else "", "ended_at": stamps[-1] if stamps else ""}
            records.append(archive_record_from_lead(lead, stub))
        return self.upsert_many(records)

    def import_csv_bytes(self, data, crm=None):
        return _import_csv_bytes(self, data, crm=crm)


def _import_csv_bytes(store, data, crm=None):
    text = data.decode("utf-8-sig") if isinstance(data, (bytes, bytearray)) else str(data or "")
    reader = csv.DictReader(StringIO(text))
    if not reader.fieldnames:
        raise ValueError("That CSV has no header row.")
    if "Prospect" not in reader.fieldnames and "When" not in reader.fieldnames:
        raise ValueError("Import a Total dials export CSV (When, Prospect, lead_id, dial_id, …).")
    archived = []
    added_to_crm = 0
    skipped = 0
    leads_by_id = {}
    if crm is not None:
        leads_by_id = {item["id"]: item for item in crm.snapshot()}
    for row in reader:
        lead_id = str(row.get("lead_id") or "").strip()
        entry = _entry_from_csv_row(row)
        lead = leads_by_id.get(lead_id)
        if lead is not None:
            if entry.get("id") and any(item.get("id") == entry["id"] for item in lead.get("call_log") or []):
                skipped += 1
                continue
            try:
                updated = crm.append_call_log(lead_id, entry)
                leads_by_id[lead_id] = updated
                added_to_crm += 1
            except (KeyError, ValueError):
                skipped += 1
            continue
        archived.append(archive_record_from_csv_row(row))
    added_archive = store.upsert_many(archived)
    return {
        "added": added_to_crm + added_archive,
        "added_crm": added_to_crm,
        "added_archive": added_archive,
        "skipped": skipped,
        "total_archive": len(store.snapshot()),
    }


def DialArchiveStore(*args, client=None, user_id=None, crm_path=None, **kwargs):
    if client is not None:
        return SupabaseDialArchiveStore(client, user_id=user_id)
    if crm_path is None and args:
        crm_path = args[0]
    return LocalDialArchiveStore(crm_path)


def dials_export_rows(leads, archived_records):
    from features._prospects.dials_csv_export import _row, _rows_for_leads

    rows = _rows_for_leads(leads)
    for record in archived_records or []:
        rows.append(_row(pseudo_lead_from_archive(record), record.get("entry") or {}))
    rows.sort(key=lambda item: item["When"], reverse=True)
    return rows

