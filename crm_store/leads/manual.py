import uuid
from datetime import timedelta

from crm_store.csv_io.fields import _phone, _timezone
from crm_store.statuses import STATUSES, utc_now

_LIMITS = {
    "name": 200,
    "business": 200,
    "timezone": 80,
    "transcript": 4000,
}


def build_manual_lead(payload, known_phones=()):
    if not isinstance(payload, dict):
        raise ValueError("Prospect details must be an object.")
    name = _text(payload.get("name"), "name")
    business = _text(payload.get("business"), "business")
    phone = _phone(payload.get("phone"))
    if not phone:
        raise ValueError("Enter a valid phone number.")
    if phone in set(known_phones):
        raise ValueError("A prospect with that phone number already exists.")
    timezone = _timezone(_text(payload.get("timezone"), "timezone")) or "Unknown"
    status = str(payload.get("status") or "new").strip() or "new"
    if status not in STATUSES:
        raise ValueError("Unknown prospect status.")
    fields = _extra_fields(payload.get("fields"))
    transcript = _transcript(_text(payload.get("transcript"), "transcript"))
    scheduled_until = (utc_now() + timedelta(hours=24)).isoformat() if status == "call" else None
    return {
        "id": str(uuid.uuid4()),
        "name": name,
        "business": business,
        "phone": phone,
        "timezone": timezone,
        "review_count": None,
        "status": status,
        "scheduled_until": scheduled_until,
        "transcript": transcript,
        "fields": fields,
        "created_at": utc_now().isoformat(),
    }


def _text(value, key):
    text = str(value or "").strip()
    limit = _LIMITS[key]
    if len(text) > limit:
        raise ValueError(f"{key.replace('_', ' ').title()} must be {limit} characters or fewer.")
    return text


def _extra_fields(raw):
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ValueError("Extra fields must be an object.")
    if len(raw) > 40:
        raise ValueError("A prospect can have at most 40 extra fields.")
    fields = {}
    for key, value in raw.items():
        label = str(key or "").strip()
        text = str(value or "").strip()
        if not label or not text:
            continue
        if len(label) > 120 or len(text) > 500:
            raise ValueError("Each extra field name must be 120 characters or fewer, and each value 500 or fewer.")
        fields[label] = text
    return fields


def _transcript(text):
    if not text:
        return []
    return [{
        "id": str(uuid.uuid4()),
        "timestamp": utc_now().isoformat(),
        "speaker": "Agent",
        "text": text,
    }]
