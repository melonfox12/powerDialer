import json
import threading
from datetime import datetime
from pathlib import Path
from crm_store.csv_io import csv_bytes_for
from crm_store.leads.parts import read_lead_parts, write_lead_parts
from crm_store.statuses import utc_now

class StorageMixin:
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
