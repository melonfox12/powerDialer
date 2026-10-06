import csv
from io import StringIO

def csv_bytes_for(leads):
    field_names = []
    for lead in leads:
        for key in lead.get("fields", {}):
            if key not in field_names and key.strip().lower() not in {
                "name", "business", "phone", "call_status", "scheduled_until", "call transcript"
            }:
                field_names.append(key)
    output = StringIO(newline="")
    headers = field_names + ["Name", "Business", "Phone", "call_status", "scheduled_until", "Call transcript"]
    writer = csv.DictWriter(output, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for lead in leads:
        row = dict(lead.get("fields", {}))
        row.update({
            "Name": lead.get("name", ""),
            "Business": lead.get("business", ""),
            "Phone": lead.get("phone", ""),
            "call_status": lead.get("status", "new"),
            "scheduled_until": lead.get("scheduled_until") or "",
            "Call transcript": "\n".join(
                f"{entry.get('timestamp', '')} {entry.get('speaker', 'Speaker')}: {entry.get('text', '')}"
                for entry in lead.get("transcript", [])
            ),
        })
        writer.writerow(row)
    return output.getvalue().encode("utf-8-sig")
