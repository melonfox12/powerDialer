"""Session trace for the local dialer. Prints to the console and debug-session.log."""

import os
import re
import threading
from datetime import datetime

LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "debug-session.log")
_lock = threading.Lock()
_enabled = False
_SECRET = re.compile(
    r"(?i)\b(authorization|bearer|api[_ ]?secret|auth[_ ]?token|password)\b\s*[:=]\s*\S+"
)


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
    return " ".join(text.split())[:500]
