from datetime import datetime, timedelta
from crm_store.csv_io import parse_csv
from crm_store.leads.manual import build_manual_lead
from crm_store.statuses import STATUSES, utc_now

class RecordMixin:
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
