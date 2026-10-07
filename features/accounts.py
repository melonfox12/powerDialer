"""Backend choice, signed-in sessions, and the Google bearer check."""

import threading
import time

from features.dialer import Dialer, TokenIndex
from features.metrics import MetricsStore, SupabaseMetricsStore
from features.prospects import ProspectStore
from features.settings import load_app_settings, save_app_settings
from shared.config import CRM_PATH, ENV_PATH, METRICS_PATH, PUBLIC_API_PATHS, read_env
from shared.infra import SupabaseClient


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
        values = read_env(ENV_PATH)
        client = SupabaseClient.from_env(values)
        self.tokens = TokenIndex()
        if client and not client.anon_key:
            raise ValueError("SUPABASE_ANON_KEY is required when Supabase storage is configured.")
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
        from features.settings import values

        user_id = getattr(dialer, "account_user_id", None)
        if not self.client or not user_id:
            return
        try:
            save_app_settings(self.client, values(dialer.env_path, dialer.account_values, signed_in=True), user_id)
        except OSError as exc:
            message = str(exc)
            if "HTTP 404" in message or "PGRST205" in message or "does not exist" in message.lower():
                raise OSError(
                    "Dialer settings could not be saved to your account. "
                    "Run docs/supabase/schema.sql in the Supabase SQL editor, then save again."
                ) from exc
            raise

    def reload_settings(self, dialer):
        user_id = getattr(dialer, "account_user_id", None)
        if not self.client or not user_id:
            return
        remote = load_app_settings(self.client, user_id)
        if remote:
            dialer.account_values.update(remote)


def resolve_account(runtime, path, authorization):
    google = bool(runtime.client and runtime.client.anon_key)
    if not google or path in PUBLIC_API_PATHS or not path.startswith("/api/"):
        return runtime.local, None
    header = authorization or ""
    token = header[7:].strip() if header.lower().startswith("bearer ") else ""
    user = runtime.client.auth_user(token)
    if not user:
        return None, {"error": "Sign in with Google to continue."}
    return runtime.session_for(user), None
