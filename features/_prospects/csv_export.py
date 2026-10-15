import csv
from io import StringIO

from features._prospects.csv_import import location_text

_STANDARD_EXPORT_FIELDS = {
    "name", "business", "state", "city", "phone", "call_status", "scheduled_until", "call transcript",
    "prospect", "company", "phone number", "timezone", "time zone", "total reviews",
    "reviews (last 30 days)", "days since last review", "30-day %", "recency source", "fit",
}

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
    headers = field_names + [
        "Name", "Business", "State", "City", "Phone",
        "Total Reviews", "Reviews (Last 30 Days)", "Days Since Last Review", "30-Day %", "Recency Source",
        "call_status", "scheduled_until", "Call transcript",
    ]
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        row = dict(lead.get("fields", {}))
        row.update({
            "Name": lead.get("name", ""),
            "Business": lead.get("business", ""),
            "State": location_text(lead, "state"),
            "City": location_text(lead, "city"),
            "Phone": lead.get("phone", ""),
            "Total Reviews": _csv_number(lead.get("review_count")),
            "Reviews (Last 30 Days)": _csv_number(lead.get("reviews_last_30_days")),
            "Days Since Last Review": _csv_number(lead.get("days_since_last_review")),
            "30-Day %": _csv_number(lead.get("review_pct_30_days")),
            "Recency Source": lead.get("recency_source") or "",
            "call_status": lead.get("status", "new"),
            "scheduled_until": lead.get("scheduled_until") or "",
            "Call transcript": "\n".join(
                f"{entry.get('timestamp', '')} {entry.get('speaker', 'Speaker')}: {entry.get('text', '')}"
                for entry in lead.get("transcript", [])
            ),
        })
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
