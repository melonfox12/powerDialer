import csv
from io import StringIO

from features._prospects.csv_import import location_text
from shared.vocabulary import canonical_status

# Column order matches the Prospects table in the web CRM (static/features/_prospects/query.js):
# LEAD_COLUMNS, then imported columns, then scheduled_until and the transcript.
_LEADING_HEADERS = [
    "Business Type", "Timezone", "First name", "Last name", "Company", "Pitch segment", "City", "State", "Business phone",
    "LinkedIn profile", "Website", "Total Reviews", "Call status",
]
_TRAILING_HEADERS = ["scheduled_until", "Call transcript"]

_STANDARD_EXPORT_FIELDS = {
    "name", "first name", "last name", "business_type", "business type", "industry", "business", "pitch segment", "state", "city", "phone",
    "call_status", "call status", "scheduled_until", "call transcript", "prospect", "company", "phone number", "business phone",
    "timezone", "time zone", "linkedin profile", "linkedin", "website", "url", "total reviews",
    "reviews (last 30 days)", "days since last review", "30-day %", "recency source", "fit",
}


def _split_name(name):
    text = str(name or "").strip()
    if not text:
        return "", ""
    space = text.find(" ")
    if space < 0:
        return text, ""
    return text[:space], text[space + 1 :].strip()


def _field_text(lead, *aliases):
    wanted = {alias.strip().casefold() for alias in aliases}
    for key, value in (lead.get("fields") or {}).items():
        if str(key).strip().casefold() in wanted:
            return str(value or "").strip()
    return ""


def _csv_number(value):
    if value is None or value == "":
        return ""
    return value


def csv_bytes_for(leads):
    field_names = []
    for lead in leads:
        for key in lead.get("fields", {}):
            if key not in field_names and key.strip().lower() not in _STANDARD_EXPORT_FIELDS:
                field_names.append(key)
    output = StringIO(newline="")
    headers = _LEADING_HEADERS + field_names + _TRAILING_HEADERS
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        row = dict(lead.get("fields", {}))
        first_name, last_name = _split_name(lead.get("name", ""))
        row.update({
            "Business Type": lead.get("business_type") or "",
            "Timezone": lead.get("timezone", ""),
            "First name": first_name,
            "Last name": last_name,
            "Company": lead.get("business", ""),
            "Pitch segment": lead.get("pitch_segment") or _field_text(
                lead, "Pitch segment", "pitch segment", "pitch_segment", "PitchSegment",
            ),
            "City": location_text(lead, "city"),
            "State": location_text(lead, "state"),
            "Business phone": lead.get("phone", ""),
            "LinkedIn profile": _field_text(lead, "LinkedIn profile", "LinkedIn", "linkedin profile", "linkedin"),
            "Website": _field_text(lead, "Website", "website", "url"),
            "Total Reviews": _csv_number(lead.get("review_count")),
            "Call status": canonical_status(lead.get("status", "new")),
            "scheduled_until": lead.get("scheduled_until") or "",
            "Call transcript": "\n".join(
                f"{entry.get('timestamp', '')} {entry.get('speaker', 'Speaker')}: {entry.get('text', '')}"
                for entry in lead.get("transcript", [])
            ),
        })
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
