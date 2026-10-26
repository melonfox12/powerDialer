"""CSV export for the Total dials call log (one row per call_log entry)."""

import csv
from io import StringIO

from shared.vocabulary import canonical_status

# Matches Total dials table columns, then prospect id/timezone, then raw call_log fields.
_HEADERS = [
    "When",
    "Prospect",
    "Phone",
    "Business",
    "Reviews",
    "Call transcript",
    "Status",
    "lead_id",
    "timezone",
    "dial_id",
    "started_at",
    "ended_at",
    "caller_id",
    "answered_by",
    "duration_seconds",
    "dial_transcript_lines",
    "connected",
    "outcome",
]


def _dial_when(entry):
    return str(entry.get("ended_at") or entry.get("started_at") or "")


def _rows_for_leads(leads):
    rows = []
    for lead in leads or []:
        lead_id = lead.get("id")
        if not lead_id:
            continue
        log = lead.get("call_log") or []
        for entry in log:
            rows.append(_row(lead, entry))
        if not log and lead.get("transcript"):
            stamps = sorted(line.get("timestamp") or "" for line in lead["transcript"] if line.get("timestamp"))
            stub = {"started_at": stamps[0] if stamps else "", "ended_at": stamps[-1] if stamps else ""}
            rows.append(_row(lead, stub))
    rows.sort(key=lambda item: item["When"], reverse=True)
    return rows


def _row(lead, entry):
    reviews = lead.get("review_count")
    transcript_count = len(lead.get("transcript") or [])
    connected = entry.get("connected")
    if connected is True:
        connected_text = "true"
    elif connected is False:
        connected_text = "false"
    else:
        connected_text = ""
    return {
        "When": _dial_when(entry),
        "Prospect": lead.get("name") or "",
        "Phone": lead.get("phone") or "",
        "Business": lead.get("business") or "",
        "Reviews": reviews if reviews is not None and reviews != "" else "",
        "Call transcript": transcript_count,
        "Status": canonical_status(lead.get("status", "new")),
        "lead_id": lead.get("id") or "",
        "timezone": lead.get("timezone") or "",
        "dial_id": str(entry.get("id") or ""),
        "started_at": str(entry.get("started_at") or ""),
        "ended_at": str(entry.get("ended_at") or ""),
        "caller_id": str(entry.get("caller_id") or ""),
        "answered_by": str(entry.get("answered_by") or ""),
        "duration_seconds": entry.get("duration_seconds") if entry.get("duration_seconds") is not None else "",
        "dial_transcript_lines": entry.get("transcript_lines") if entry.get("transcript_lines") is not None else "",
        "connected": connected_text,
        "outcome": str(entry.get("outcome") or ""),
    }


def dials_csv_bytes_for(leads):
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=_HEADERS, extrasaction="ignore")
    writer.writeheader()
    for row in _rows_for_leads(leads):
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
