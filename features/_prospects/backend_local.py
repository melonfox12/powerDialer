"""Local JSON prospect persistence. Rules live in features.prospects."""

import json
import threading
from datetime import datetime
from pathlib import Path

from features._prospects.csv_export import csv_bytes_for
from features._prospects.csv_import import build_manual_lead, parse_csv
from shared.infra import utc_now

PART_LINE_LIMIT = 150


def json_line_count(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").count("\n")


def lead_chunks(leads, limit=PART_LINE_LIMIT):
    chunks = []
    current = []
    for lead in leads:
        if current and json_line_count(current + [lead]) > limit:
            chunks.append(current)
            current = [lead]
        else:
            current.append(lead)
    if current or not chunks:
        chunks.append(current)
    return chunks


def read_lead_parts(directory):
    leads = []
    for path in sorted(Path(directory).glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            leads.extend(data)
        elif isinstance(data, dict):
            leads.append(data)
    return leads


def write_lead_parts(directory, leads, limit=PART_LINE_LIMIT):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    chunks = lead_chunks(leads, limit)
    written = set()
    for index, chunk in enumerate(chunks, start=1):
        name = f"part-{index:02d}.json"
        path = directory / name
        temp_path = path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(chunk, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_path.replace(path)
        written.add(name)
    for path in directory.glob("*.json"):
        if path.name not in written:
            path.unlink()

class LocalBackend:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.leads = []
        self.revision = 0
        self.load()

    def _stores_parts(self):
        return self.path.is_dir() or self.path.suffix == ""

    def load(self):
        with self.lock:
            try:
                if self.path.is_dir():
                    self.leads = read_lead_parts(self.path)
                elif self.path.is_file():
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    self.leads = data if isinstance(data, list) else []
            except (OSError, json.JSONDecodeError):
                self.leads = []
            self.expire_due(save=False)

    def save(self):
        with self.lock:
            if self._stores_parts():
                write_lead_parts(self.path, self.leads)
            else:
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

    def add_lead(self, payload):
        with self.lock:
            self.expire_due(save=False)
            lead = build_manual_lead(payload, (item["phone"] for item in self.leads))
            self.leads.append(lead)
            self.save()
            return dict(lead)

    def add_csv(self, data):
        with self.lock:
            self.expire_due(save=False)
            leads, info = parse_csv(data, (lead["phone"] for lead in self.leads))
            self.leads.extend(leads)
            self.save()
            info["added"] = len(leads)
            info["total"] = len(self.leads)
            return info



    def leads_locked(self):
        return self.leads

    def expire_locked(self, leads):
        self.expire_due(save=False)

    def save_locked(self, lead):
        for index, item in enumerate(self.leads):
            if item["id"] == lead["id"]:
                self.leads[index] = lead
        self.save()

    def remove(self, lead_id):
        with self.lock:
            original_count = len(self.leads)
            self.leads = [lead for lead in self.leads if lead["id"] != lead_id]
            if len(self.leads) == original_count:
                raise KeyError("Prospect not found")
            self.save()
