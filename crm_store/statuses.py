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

from shared.vocabulary import STATUS_KEYS, TIMEZONE_ALIASES, UTC_OFFSET_ZONES
from shared.infra import utc_now

STATUSES = STATUS_KEYS
PHONE_HEADER_WORDS = ("phone", "mobile", "cell", "tel", "number", "whatsapp")
BUSINESS_HEADER_WORDS = ("business", "company", "organization", "organisation", "employer", "account", "firm")
TIMEZONE_HEADER_WORDS = ("timezone", "time zone", "tz")
REVIEW_HEADER_WORDS = ("review", "rating count", "num reviews", "num_reviews")

TIMEZONE_ABBREVIATION = re.compile(r"\b(e[sd]t|c[sd]t|m[sd]t|p[sd]t|akst|akdt|hst)\b", re.I)
JUNK_HEADER = re.compile(r"\b(e-?mail|address|street|city|state|zip|postal|country|url|website|linkedin|notes?|status|id|title|industry|revenue|source|date|fax)\b", re.I)
SCIENTIFIC_NUMBER = re.compile(r"^(\d)(?:\.(\d+))?[eE]\+?(\d+)$")

