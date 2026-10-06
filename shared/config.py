"""Paths, ports, and .env read/write."""

import json
import os

from shared.vocabulary import ENV_KEYS, SETTING_DEFAULTS

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(APP_DIR, "static")
CRM_PATH = os.path.join(APP_DIR, "crm_data")
METRICS_PATH = os.path.join(APP_DIR, "metrics.json")
ENV_PATH = os.path.join(APP_DIR, ".env")
APP_HOST = "127.0.0.1"
APP_PORT = 8000
HOOK_HOST = "127.0.0.1"
HOOK_PORT = 8765
MAX_BODY = 12 * 1024 * 1024
PUBLIC_API_PATHS = {"/api/health", "/api/auth/config", "/api/debug"}
QUIET_HTTP = {
    "/", "/index.html", "/static/", "/static/index.html",
    "/app.css", "/app.js", "/static/app.css", "/static/app.js",
    "/api/live", "/api/state", "/api/metrics", "/api/health", "/api/debug",
}


def read_env(path):
    values = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as env_file:
            for line in env_file:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key == "OPENING_SCRIPT":
                        try:
                            value = json.loads(value)
                        except json.JSONDecodeError:
                            pass
                    else:
                        value = value.strip('"').strip("'")
                    values[key] = value
    for key in ENV_KEYS:
        values.setdefault(key, os.environ.get(key, ""))
    return values


def write_env(path, updates):
    values = read_env(path)
    for key, value in updates.items():
        stripped = str(value).strip()
        if key == "OPENING_SCRIPT":
            values[key] = json.dumps(stripped, ensure_ascii=False)
        elif stripped:
            values[key] = stripped
        elif key in SETTING_DEFAULTS:
            values[key] = SETTING_DEFAULTS[key]
        else:
            values[key] = ""
    lines = [f"{key}={value}" for key, value in values.items() if value]
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as env_file:
        env_file.write("\n".join(lines) + "\n")
    os.replace(temp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return values
