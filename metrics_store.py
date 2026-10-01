"""Lightweight daily / all-time dialing metrics, persisted as JSON."""

import json
import threading
from datetime import timedelta
from pathlib import Path

from crm_store import utc_now


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
