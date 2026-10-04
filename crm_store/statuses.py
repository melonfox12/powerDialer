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

STATUSES = ("new", "call", "disqualified", "booked", "interested", "do_not_call")
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

