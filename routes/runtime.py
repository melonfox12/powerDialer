"""Account sessions for the local app server."""

import threading
import time

from features.prospects import ProspectStore
from features.metrics import MetricsStore, SupabaseMetricsStore
from shared.config import (
    APP_HOST,
    APP_PORT,
    CRM_PATH,
    ENV_PATH,
    HOOK_HOST,
    HOOK_PORT,
    MAX_BODY,
    METRICS_PATH,
    PUBLIC_API_PATHS,
    QUIET_HTTP,
    STATIC_DIR,
)
from features.dialer import Dialer, TokenIndex


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

    def configure(self):
        from shared.config import read_env
        from supabase_store import SupabaseClient

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
            crm = ProspectStore(CRM_PATH)
            metrics = MetricsStore(METRICS_PATH)
            dialer = Dialer(crm, ENV_PATH, metrics=metrics)
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
        from features.settings import load_app_settings

        crm = ProspectStore(client=self.client, user_id=user_id)
        metrics = SupabaseMetricsStore(self.client, user_id=user_id)
        dialer = Dialer(crm, ENV_PATH, metrics=metrics)
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
        from features.settings import persist_settings

        return persist_settings(self, dialer)

    def reload_settings(self, dialer):
        from features.settings import reload_settings

        return reload_settings(self, dialer)
