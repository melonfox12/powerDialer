"""CSV import, header detection, and manual prospect construction."""

import csv
import re
import uuid
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from io import StringIO

from shared.infra import utc_now
from shared.vocabulary import STATUS_KEYS, TIMEZONE_ALIASES, UTC_OFFSET_ZONES

STATUSES = STATUS_KEYS
PHONE_HEADER_WORDS = ("phone", "mobile", "cell", "tel", "number", "whatsapp")
BUSINESS_HEADER_WORDS = ("business", "company", "organization", "organisation", "employer", "account", "firm")
TIMEZONE_HEADER_WORDS = ("timezone", "time zone", "tz")
REVIEW_HEADER_WORDS = ("review", "rating count", "num reviews", "num_reviews")

TIMEZONE_ABBREVIATION = re.compile(r"\b(e[sd]t|c[sd]t|m[sd]t|p[sd]t|akst|akdt|hst)\b", re.I)
STATE_HEADER = re.compile(r"\bstate\b", re.I)
CITY_HEADER = re.compile(r"\bcity\b", re.I)
JUNK_HEADER = re.compile(r"\b(e-?mail|address|street|city|state|zip|postal|country|url|website|linkedin|notes?|status|id|title|industry|revenue|source|date|fax)\b", re.I)
SCIENTIFIC_NUMBER = re.compile(r"^(\d)(?:\.(\d+))?[eE]\+?(\d+)$")


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

def _choose_dialect(text):
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel
    first = next((line for line in sample.splitlines() if line.strip()), "")
    if first.count(dialect.delimiter) == 0 and first.count(",") > 0:
        return csv.excel
    return dialect

def _read_csv(data):
    if isinstance(data, str):
        text = data
    else:
        payload = bytes(data).replace(b"\x00", b"")
        text = None
        for encoding in ("utf-8-sig", "utf-16", "cp1252"):
            try:
                text = payload.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            text = payload.decode("latin-1")
    text = text.replace("\x00", "").strip()
    if not text:
        return []
    dialect = _choose_dialect(text)
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
    state_column = _header_column(header, used, STATE_HEADER)
    if state_column is not None:
        used.add(state_column)
    city_column = _header_column(header, used, CITY_HEADER)
    if city_column is not None:
        used.add(city_column)
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
        located = {index for index in (state_column, city_column) if index is not None}
        fields = {headers[index]: value for index, value in enumerate(row) if value and index not in located}
        timezone = _timezone(row[timezone_column]) if timezone_column is not None else None
        review_count = _review_count(row[review_column]) if review_column is not None else None
        leads.append({
            "id": str(uuid.uuid4()),
            "name": name,
            "business": row[business_column].strip() if business_column is not None else "",
            "state": row[state_column].strip() if state_column is not None else "",
            "city": row[city_column].strip() if city_column is not None else "",
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

_LIMITS = {
    "name": 200,
    "business": 200,
    "state": 80,
    "city": 120,
    "timezone": 80,
    "transcript": 4000,
}


def build_manual_lead(payload, known_phones=()):
    if not isinstance(payload, dict):
        raise ValueError("Prospect details must be an object.")
    name = _text(payload.get("name"), "name")
    business = _text(payload.get("business"), "business")
    state = _text(payload.get("state"), "state")
    city = _text(payload.get("city"), "city")
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
        "state": state,
        "city": city,
        "phone": phone,
        "timezone": timezone,
        "review_count": None,
        "status": status,
        "scheduled_until": scheduled_until,
        "transcript": transcript,
        "fields": fields,
        "created_at": utc_now().isoformat(),
    }


def update_lead_fields(lead, payload, known_phones=()):
    if not isinstance(payload, dict):
        raise ValueError("Prospect details must be an object.")
    changed = False
    if "name" in payload:
        lead["name"] = _text(payload.get("name"), "name")
        changed = True
    if "business" in payload:
        lead["business"] = _text(payload.get("business"), "business")
        changed = True
    if "state" in payload:
        lead["state"] = _text(payload.get("state"), "state")
        _forget_location_alias(lead, "state")
        changed = True
    if "city" in payload:
        lead["city"] = _text(payload.get("city"), "city")
        _forget_location_alias(lead, "city")
        changed = True
    if "phone" in payload:
        phone = _phone(payload.get("phone"))
        if not phone:
            raise ValueError("Enter a valid phone number.")
        if phone in set(known_phones):
            raise ValueError("A prospect with that phone number already exists.")
        lead["phone"] = phone
        changed = True
    if "timezone" in payload:
        lead["timezone"] = _timezone(_text(payload.get("timezone"), "timezone")) or "Unknown"
        changed = True
    if "fields" in payload:
        lead["fields"] = _merged_fields(lead.get("fields"), payload.get("fields"))
        changed = True
    if not changed:
        raise ValueError("No prospect fields to update.")
    return lead


def _header_column(header, used, pattern):
    if not header:
        return None
    return next((index for index, value in enumerate(header) if index not in used and pattern.search(value)), None)


def location_text(lead, key):
    direct = str((lead or {}).get(key) or "").strip()
    if direct:
        return direct
    for name, value in ((lead or {}).get("fields") or {}).items():
        if str(name).strip().lower() == key:
            return str(value or "").strip()
    return ""


def _forget_location_alias(lead, key):
    fields = lead.get("fields") or {}
    cleaned = {name: value for name, value in fields.items() if str(name).strip().lower() != key}
    if cleaned != fields:
        lead["fields"] = cleaned


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
    return _merged_fields({}, raw)


def _merged_fields(current, raw):
    if not isinstance(raw, dict):
        raise ValueError("Extra fields must be an object.")
    fields = dict(current or {})
    for key, value in raw.items():
        label = str(key or "").strip()
        text = str(value or "").strip()
        if not label:
            continue
        if not text:
            fields.pop(label, None)
            continue
        if len(label) > 120 or len(text) > 500:
            raise ValueError("Each extra field name must be 120 characters or fewer, and each value 500 or fewer.")
        fields[label] = text
    if len(fields) > 40:
        raise ValueError("A prospect can have at most 40 extra fields.")
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
