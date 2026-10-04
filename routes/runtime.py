"""Account sessions for the local app server."""

import os
import threading
import time

from crm_store import CRMStore
from metrics_store import MetricsStore
from twilio_calls import TokenIndex, TwilioDialer

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(APP_DIR, "static")
CRM_PATH = os.path.join(APP_DIR, "crm_data.json")
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
class Account:
    def __init__(self, crm, metrics, dialer):
        self.crm = crm
        self.metrics = metrics
        self.dialer = dialer


class AppRuntime:
    def __init__(self):
        self.client = None
        self.storage_name = "local JSON files"
        self.local = None
        self.sessions = {}
        self.session_lock = threading.Lock()
        self.tokens = TokenIndex()
        self._health_at = 0
        self._health = {"ok": True, "storage": self.storage_name}

    def configure(self, migrate=False):
        from supabase_store import SupabaseClient
        from twilio_calls import read_env

        values = read_env(ENV_PATH)
        client = SupabaseClient.from_env(values)
        self.tokens = TokenIndex()
        if client:
            self.client = client
            self.storage_name = "Supabase"
            self.local = None
            self._ping()
        else:
            self.client = None
            self.storage_name = "local JSON files"
            crm = CRMStore(CRM_PATH)
            metrics = MetricsStore(METRICS_PATH)
            dialer = TwilioDialer(crm, ENV_PATH, metrics=metrics)
            dialer.storage_name = self.storage_name
            dialer.token_index = self.tokens
            self.local = Account(crm, metrics, dialer)
        self._health = {"ok": True, "storage": self.storage_name}
        return self

    def _ping(self):
        self.client.request("GET", "prospects", {"select": "id", "limit": "1"})

    def health(self):
        if not self.client:
            return {"ok": True, "storage": self.storage_name}
        now = time.time()
        if now - self._health_at < 30:
            return self._health
        try:
            self._ping()
        except OSError as exc:
            self._health = {"ok": False, "storage": self.storage_name, "error": str(exc)}
        else:
            self._health = {"ok": True, "storage": self.storage_name}
        self._health_at = now
        return self._health

    def session_for(self, user):
        user_id = user["id"]
        with self.session_lock:
            existing = self.sessions.get(user_id)
        if existing:
            existing.dialer.account_email = user.get("email") or existing.dialer.account_email
            return existing
        from supabase_store import SupabaseCRMStore, SupabaseMetricsStore, load_app_settings

        crm = SupabaseCRMStore(self.client, user_id=user_id)
        metrics = SupabaseMetricsStore(self.client, user_id=user_id)
        dialer = TwilioDialer(crm, ENV_PATH, metrics=metrics)
        dialer.storage_name = "Supabase"
        dialer.token_index = self.tokens
        dialer.account_user_id = user_id
        dialer.account_email = user.get("email") or ""
        dialer.account_values = load_app_settings(self.client, user_id)
        dialer.settings_saver = lambda active: self.persist_settings(active)
        account = Account(crm, metrics, dialer)
        with self.session_lock:
            current = self.sessions.get(user_id)
            if current:
                return current
            self.sessions[user_id] = account
        return account

    def persist_settings(self, dialer):
        from supabase_store import save_app_settings

        user_id = getattr(dialer, "account_user_id", None)
        if not self.client or not user_id:
            return
        try:
            save_app_settings(self.client, dialer._values(), user_id)
        except OSError as exc:
            message = str(exc)
            if "HTTP 404" in message or "PGRST205" in message or "does not exist" in message.lower():
                raise OSError(
                    "Dialer settings could not be saved to your account. "
                    "Run supabase_schema.sql in the Supabase SQL editor, then save again."
                ) from exc
            raise

    def reload_settings(self, dialer):
        from supabase_store import load_app_settings

        user_id = getattr(dialer, "account_user_id", None)
        if not self.client or not user_id:
            return
        remote = load_app_settings(self.client, user_id)
        if remote:
            dialer.account_values.update(remote)
