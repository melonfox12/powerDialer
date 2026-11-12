#!/usr/bin/env python3
"""CLI entry for the AI media bridge (same logic as embedded server thread)."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from features.ai_media_bridge import run_blocking
from shared.config import APP_HOST, APP_PORT

APP_URL = os.environ.get("AI_BRIDGE_APP_URL", f"http://{APP_HOST}:{APP_PORT}").rstrip("/")
SECRET = os.environ.get("AI_BRIDGE_SECRET", "")
HOST = os.environ.get("AI_BRIDGE_HOST", "0.0.0.0")
PORT = int(os.environ.get("AI_BRIDGE_PORT", "8766"))

if __name__ == "__main__":
    if not SECRET:
        print("Set AI_BRIDGE_SECRET in the environment.", file=sys.stderr)
        sys.exit(1)
    try:
        run_blocking(HOST, PORT, APP_URL, SECRET)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        sys.exit(1)
