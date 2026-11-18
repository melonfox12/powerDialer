# -----------------------------------------------------------------------------
# File: shared/config.py
# Purpose: Application paths, listen ports, env file I/O, and auth bypass lists.
# Exports: APP_DIR, STATIC_DIR, CRM_PATH, METRICS_PATH, ENV_PATH, hosts/ports,
#          PUBLIC_API_PATHS, QUIET_HTTP, read_env, write_env.
# Imported by: server.py, web.py, features/*, scripts/*.
# Depends on: shared.vocabulary.ENV_KEYS, SETTING_DEFAULTS
# -----------------------------------------------------------------------------
"""Paths, ports, and .env read/write."""

import json
import os

# Pull canonical setting key lists from vocabulary (single source of truth).
from shared.vocabulary import ENV_KEYS, SETTING_DEFAULTS

# Repository root: parent of shared/ (this file lives in shared/config.py).
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# Frontend static tree served by _web/respond.py.
STATIC_DIR = os.path.join(APP_DIR, "static")
# Local-mode CRM JSON directory (never touch in automation per project rules).
CRM_PATH = os.path.join(APP_DIR, "crm_data")
# Local-mode metrics bump file path.
METRICS_PATH = os.path.join(APP_DIR, "metrics.json")
# Twilio + Supabase + app secrets on disk (read by read_env; chmod 600 on write).
ENV_PATH = os.path.join(APP_DIR, ".env")
# Main CRM + API server bind address (browser hits this).
APP_HOST = "127.0.0.1"
APP_PORT = 8000
# Twilio webhook-only server bind address (expose via HTTPS tunnel separately).
HOOK_HOST = "127.0.0.1"
HOOK_PORT = 8765
# Upper bound for POST bodies elsewhere in the stack (guards large uploads).
MAX_BODY = 12 * 1024 * 1024
# API paths that skip normal Google/Supabase bearer auth (see features/accounts resolve_account).
PUBLIC_API_PATHS = {
    "/api/health",
    "/api/auth/config",
    "/api/debug",
    "/api/ai-voice/bootstrap",
    "/api/ai-voice/stream-started",
    "/api/ai-voice/stream-sync",
    "/api/ai-voice/stream-stopped",
    "/api/ai-voice/inbound",
}
# Request paths omitted from verbose HTTP debug logging in respond.py.
QUIET_HTTP = {
    "/", "/index.html", "/static/", "/static/index.html",
    "/app.css", "/app.js", "/static/app.css", "/static/app.js",
    "/api/live", "/api/state", "/api/leads", "/api/metrics", "/api/performance", "/api/health", "/api/debug",
}


# Load key/value settings from a .env file, then fill missing keys from os.environ.
def read_env(path):
    values = {}
    # Parse line-based .env if present (does not use python-dotenv dependency).
    if os.path.exists(path):
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                # Skip blanks and comments; require KEY=value shape.
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    # OPENING_SCRIPT is stored JSON-encoded on disk for multiline scripts.
                    if key == "OPENING_SCRIPT":
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                    elif key == "PIPELINE_CUSTOM_STEPS_JSON":
                        try:
                            parsed = json.loads(value)
                            if isinstance(parsed, list):
                                value = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
                            else:
                                value = ""
                        except json.JSONDecodeError:
                            value = ""
                    else:
                        # Strip optional surrounding quotes from .env values.
                        value = value.strip('"').strip("'")
                    values[key] = value
    # Every known env key gets a default from process environment if not in file.
    for key in ENV_KEYS:
        values.setdefault(key, os.environ.get(key, ""))
    return values


# Merge updates into .env atomically; return in-memory dict with OPENING_SCRIPT decoded.
def write_env(path, updates):
    values = read_env(path)
    for key, value in updates.items():
        stripped = str(value).strip()
        if key == "OPENING_SCRIPT":
            values[key] = json.dumps(stripped, ensure_ascii=False)
        elif key == "PIPELINE_CUSTOM_STEPS_JSON":
            if isinstance(value, (list, dict)):
                values[key] = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value else ""
            else:
                values[key] = stripped
        elif stripped:
            values[key] = stripped
        elif key in SETTING_DEFAULTS:
            # Clearing a known setting restores vocabulary default literal.
            values[key] = SETTING_DEFAULTS[key]
        else:
            values[key] = ""
    # Only non-empty values are written to disk (compact .env).
    lines = [f"{key}={value}" for key, value in values.items() if value]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    # Callers use the return value as in-memory prefs; OPENING_SCRIPT is JSON-encoded on disk only.
    merged = dict(values)
    if "OPENING_SCRIPT" in merged:
        raw = merged["OPENING_SCRIPT"]
        if isinstance(raw, str):
            try:
                merged["OPENING_SCRIPT"] = json.loads(raw)
            except json.JSONDecodeError:
                pass
    return merged