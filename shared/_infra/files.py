"""Debug log, UTC clock, and atomic JSON writes."""

import os
import re
import threading
from datetime import datetime, timezone

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "debug-session.log")
_lock = threading.Lock()
_enabled = False
_SECRET = re.compile(
    r"(?i)(authorization|api[_ ]?secret|auth[_ ]?token|secret[_ ]?key|password)"
    r"['\"]?\s*[:=]\s*['\"]?(?:(?:bearer|basic)\s+)?[^\s'\",;]+"
)
_BEARER = re.compile(r"(?i)\bbearer\s+[^\s'\",;]+")
_SUPABASE_KEY = re.compile(r"\bsb_secret_[^\s'\",;]*")


def utc_now():
    return datetime.now(timezone.utc)


def enable():
    global _enabled
    _enabled = True
    with _lock:
        with open(LOG_PATH, "w", encoding="utf-8") as handle:
            handle.write("")
    debug_event("session", "debug log started", LOG_PATH)


def debug_event(kind, message, detail=""):
    if not _enabled:
        return
    stamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    text = _redact(message)
    extra = _redact(detail)
    line = f"{stamp} {str(kind).upper():<7} {text}"
    if extra:
        line += f" — {extra}"
    with _lock:
        print(line, flush=True)
        with open(LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _redact(value):
    text = _SECRET.sub(lambda match: f"{match.group(1)}=[redacted]", str(value or ""))
    text = _BEARER.sub("Bearer [redacted]", text)
    text = _SUPABASE_KEY.sub("[redacted]", text)
    return " ".join(text.split())[:500]


def write_json_atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(text, encoding="utf-8")
    temp_path.replace(path)
