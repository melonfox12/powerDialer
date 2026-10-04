import csv
import re
from decimal import Decimal, InvalidOperation
from io import StringIO
from crm_store.statuses import SCIENTIFIC_NUMBER, TIMEZONE_ABBREVIATION, TIMEZONE_ALIASES, UTC_OFFSET_ZONES

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
