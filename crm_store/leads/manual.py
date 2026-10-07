import uuid
from datetime import timedelta

from crm_store.csv_io.fields import _phone, _review_count, _timezone
from crm_store.statuses import REVIEW_HEADER_WORDS, STATUSES, utc_now


def build_manual_lead(data, known_phones=()):
    if not isinstance(data, dict):
        raise ValueError("Prospect details must be an object.")
    phone = _phone(data.get("phone"))
    if not phone:
        raise ValueError("Enter a usable phone number.")
    if phone in {str(item or "") for item in known_phones}:
        raise ValueError("A prospect with that phone number already exists.")
    status = str(data.get("status") or "new").strip() or "new"
    if status not in STATUSES:
        raise ValueError("Unknown prospect status.")
    raw_fields = data.get("fields") or {}
    if not isinstance(raw_fields, dict):
        raise ValueError("Extra fields must be an object.")
    fields = {}
    for key, value in raw_fields.items():
        label = str(key or "").strip()
        text = str(value or "").strip()
        if label and text:
            fields[label] = text
    review_count = None
    for key, value in fields.items():
        if any(word in key.lower() for word in REVIEW_HEADER_WORDS):
            review_count = _review_count(value)
            break
    transcript_text = str(data.get("transcript") or "").strip()
    created_at = utc_now()
    transcript = []
    if transcript_text:
        transcript.append({
            "id": str(uuid.uuid4()),
            "timestamp": created_at.isoformat(),
            "speaker": "Prospect",
            "text": transcript_text,
        })
    return {
        "id": str(uuid.uuid4()),
        "name": str(data.get("name") or "").strip(),
        "business": str(data.get("business") or "").strip(),
        "phone": phone,
        "timezone": _timezone(data.get("timezone")) or "Unknown",
        "review_count": review_count,
        "status": status,
        "scheduled_until": (created_at + timedelta(hours=24)).isoformat() if status == "call" else None,
        "transcript": transcript,
        "fields": fields,
        "created_at": created_at.isoformat(),
    }
