"""Persistent CRM records and flexible CSV import/export."""

import csv
import json
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import StringIO
from pathlib import Path

STATUSES = ("new", "call", "disqualified", "booked")
PHONE_HEADER_WORDS = ("phone", "mobile", "cell", "tel", "number", "whatsapp")
BUSINESS_HEADER_WORDS = ("business", "company", "organization", "organisation", "employer", "account", "firm")
TIMEZONE_HEADER_WORDS = ("timezone", "time zone", "tz")
REVIEW_HEADER_WORDS = ("review", "rating count", "num reviews", "num_reviews")

TIMEZONE_ALIASES = {
    "eastern": "Eastern", "est": "Eastern", "edt": "Eastern", "et": "Eastern",
    "america/new_york": "Eastern", "america/detroit": "Eastern", "america/indianapolis": "Eastern",
    "central": "Central", "cst": "Central", "cdt": "Central", "ct": "Central",
    "america/chicago": "Central",
    "mountain": "Mountain", "mst": "Mountain", "mdt": "Mountain", "mt": "Mountain",
    "america/denver": "Mountain", "america/phoenix": "Mountain",
    "pacific": "Pacific", "pst": "Pacific", "pdt": "Pacific", "pt": "Pacific",
    "america/los_angeles": "Pacific",
    "alaska": "Alaska", "akst": "Alaska", "akdt": "Alaska", "america/anchorage": "Alaska",
    "hawaii": "Hawaii", "hst": "Hawaii", "pacific/honolulu": "Hawaii",
}
UTC_OFFSET_ZONES = {-5: "Eastern", -6: "Central", -7: "Mountain", -8: "Pacific", -9: "Alaska", -10: "Hawaii"}
TIMEZONE_ABBREVIATION = re.compile(r"\b(e[sd]t|c[sd]t|m[sd]t|p[sd]t|akst|akdt|hst)\b", re.I)
JUNK_HEADER = re.compile(r"\b(e-?mail|address|street|city|state|zip|postal|country|url|website|linkedin|notes?|status|id|title|industry|revenue|source|date|fax)\b", re.I)
SCIENTIFIC_NUMBER = re.compile(r"^(\d)(?:\.(\d+))?[eE]\+?(\d+)$")


def utc_now():
    return datetime.now(timezone.utc)


def _phone(value):
    text = str(value or "").strip()
    text = re.sub(r"^(?:tel|phone|mobile|cell)\s*:\s*", "", text, flags=re.I)
    text = re.sub(r"\s*(?:ext\.?|extension|x|#)\s*\d{1,6}\s*$", "", text, flags=re.I)
    scientific = SCIENTIFIC_NUMBER.match(text)
    if scientific:
        if len(scientific.group(1) + (scientific.group(2) or "")) < int(scientific.group(3)) + 1:
            return None
        try:
            text = str(int(Decimal(text)))
        except (InvalidOperation, OverflowError):
            return None
    elif re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if not re.fullmatch(r"\+?[\d\s().\-]+", text):
        return None
    digits = re.sub(r"\D", "", text)
    if text.startswith("00"):
        return "+" + digits[2:] if 8 <= len(digits) - 2 <= 15 else None
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def _timezone(value):
    text = str(value or "").strip()
    if not text:
        return None
    lower = text.lower()
    alias = TIMEZONE_ALIASES.get(lower) or TIMEZONE_ALIASES.get(lower.replace(" ", "_"))
    if alias:
        return alias
    for word, zone in (("eastern", "Eastern"), ("central", "Central"), ("mountain", "Mountain"),
                       ("pacific", "Pacific"), ("alaska", "Alaska"), ("hawaii", "Hawaii")):
        if word in lower:
            return zone
    abbrev = TIMEZONE_ABBREVIATION.search(lower)
    if abbrev:
        zone = TIMEZONE_ALIASES.get(abbrev.group(1))
        if zone:
            return zone
    if "utc" in lower or "gmt" in lower or re.fullmatch(r"[+-]\d{1,2}(:?\d{2})?", text):
        offset = re.search(r"([+-])\s?(\d{1,2})(?::?\d{2})?", text)
        if offset:
            hours = (-1 if offset.group(1) == "-" else 1) * int(offset.group(2))
            zone = UTC_OFFSET_ZONES.get(hours)
            if zone:
                return zone
    return text


def _review_count(value):
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"-?\d+", text.replace(",", ""))
    if not match:
        return None
    try:
        return int(match.group())
    except ValueError:
        return None


def _read_csv(data):
    text = None
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("latin-1")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    return [[cell.strip() for cell in row] for row in csv.reader(StringIO(text), dialect)
            if any(cell.strip() for cell in row)]


def _unique_headers(headers):
    seen = {}
    result = []
    for index, header in enumerate(headers):
        base = header.strip() or f"Column {index + 1}"
        seen[base] = seen.get(base, 0) + 1
        result.append(base if seen[base] == 1 else f"{base} ({seen[base]})")
    return result


def parse_csv(data, known_phones=()):
    rows = _read_csv(data)
    if not rows:
        return [], {"duplicates": 0, "skipped": 0, "columns": []}

    width = max(map(len, rows))
    rows = [row + [""] * (width - len(row)) for row in rows]
    first_has_phone = any(_phone(value) for value in rows[0])
    header = None if first_has_phone else _unique_headers(rows[0])
    records = rows[1:] if header else rows
    headers = header or [f"Column {index + 1}" for index in range(width)]
    hits = [sum(bool(_phone(row[column])) for row in records) for column in range(width)]

    phone_columns = []
    if header:
        phone_columns = [index for index, value in enumerate(header)
                         if any(word in value.lower() for word in PHONE_HEADER_WORDS)
                         and "fax" not in value.lower() and hits[index]]
    if not phone_columns and max(hits, default=0):
        phone_columns = [hits.index(max(hits))]

    used = set(phone_columns)
    first_name = next((i for i, value in enumerate(header or [])
                       if "first" in value.lower() and i not in used), None)
    last_name = next((i for i, value in enumerate(header or [])
                      if "last" in value.lower() and "name" in value.lower() and i not in used), None)
    full_name = next((i for i, value in enumerate(header or [])
                      if ("name" in value.lower() or "contact" in value.lower()) and i not in used
                      and i not in (first_name, last_name)), None)
    name_column = full_name
    business_column = next((i for i, value in enumerate(header or [])
                            if i not in used and any(word in value.lower() for word in BUSINESS_HEADER_WORDS)), None)
    if first_name is not None and last_name is not None:
        used.update((first_name, last_name))
    elif name_column is not None:
        used.add(name_column)
    if business_column is not None:
        used.add(business_column)
    timezone_column = next((i for i, value in enumerate(header or [])
                            if i not in used and any(word in value.lower() for word in TIMEZONE_HEADER_WORDS)), None)
    if timezone_column is not None:
        used.add(timezone_column)
    review_column = next((i for i, value in enumerate(header or [])
                          if i not in used and any(word in value.lower() for word in REVIEW_HEADER_WORDS)), None)
    if review_column is not None:
        used.add(review_column)

    text_columns = [i for i in range(width) if i not in used and hits[i] <= len(records) // 2
                    and not (header and JUNK_HEADER.search(header[i]))]
    if name_column is None and first_name is None and text_columns:
        name_column = text_columns.pop(0)
    if business_column is None and text_columns:
        business_column = text_columns.pop(0)

    seen = set(known_phones)
    leads = []
    duplicates = skipped = 0
    for row in records:
        phone = next((_phone(row[index]) for index in phone_columns if _phone(row[index])), None)
        if not phone:
            phone = next((_phone(value) for value in row if _phone(value)), None)
        if not phone:
            skipped += 1
            continue
        if phone in seen:
            duplicates += 1
            continue
        seen.add(phone)
        if first_name is not None and last_name is not None:
            name = f"{row[first_name]} {row[last_name]}".strip()
        else:
            name = row[name_column].strip() if name_column is not None else ""
        fields = {headers[index]: value for index, value in enumerate(row) if value}
        timezone = _timezone(row[timezone_column]) if timezone_column is not None else None
        review_count = _review_count(row[review_column]) if review_column is not None else None
        leads.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "business": row[business_column].strip() if business_column is not None else "",
            "phone": phone,
            "timezone": timezone or "Unknown",
            "review_count": review_count,
            "status": "new",
            "scheduled_until": None,
            "transcript": [],
            "fields": fields,
            "created_at": utc_now().isoformat(),
        })
    return leads, {"duplicates": duplicates, "skipped": skipped, "columns": headers}


class CRMStore:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.leads = []
        self.load()

    def load(self):
        with self.lock:
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    self.leads = data if isinstance(data, list) else []
                except (OSError, json.JSONDecodeError):
                    self.leads = []
            self.expire_due(save=False)

    def save(self):
        with self.lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
            temp_path.write_text(json.dumps(self.leads, ensure_ascii=False, indent=2), encoding="utf-8")
            temp_path.replace(self.path)

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

    def add_csv(self, data):
        with self.lock:
            self.expire_due(save=False)
            leads, info = parse_csv(data, (lead["phone"] for lead in self.leads))
            self.leads.extend(leads)
            self.save()
            info["added"] = len(leads)
            info["total"] = len(self.leads)
            return info

    def set_status(self, lead_id, status):
        if status not in STATUSES:
            raise ValueError("Unknown prospect status")
        with self.lock:
            self.expire_due(save=False)
            lead = next((item for item in self.leads if item["id"] == lead_id), None)
            if lead is None:
                raise KeyError("Prospect not found")
            lead["status"] = status
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

    def remove(self, lead_id):
        with self.lock:
            original_count = len(self.leads)
            self.leads = [lead for lead in self.leads if lead["id"] != lead_id]
            if len(self.leads) == original_count:
                raise KeyError("Prospect not found")
            self.save()

    def snapshot(self):
        self.expire_due()
        with self.lock:
            return [dict(lead) for lead in self.leads]

    def timezone_groups(self):
        counts = {}
        for lead in self.snapshot():
            if lead["status"] != "new":
                continue
            tz = lead.get("timezone") or "Unknown"
            counts[tz] = counts.get(tz, 0) + 1
        return sorted(counts.items(), key=lambda item: (item[0] == "Unknown", -item[1], item[0]))

    def csv_bytes(self):
        leads = self.snapshot()
        field_names = []
        for lead in leads:
            for key in lead.get("fields", {}):
                if key not in field_names and key.strip().lower() not in {
                    "name", "business", "phone", "call_status", "scheduled_until"
                }:
                    field_names.append(key)
        output = StringIO(newline="")
        headers = field_names + ["Name", "Business", "Phone", "call_status", "scheduled_until"]
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
            })
            writer.writerow(row)
        return output.getvalue().encode("utf-8-sig")