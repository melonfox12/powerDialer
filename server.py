"""Local web application and public Twilio callback servers."""

import json
import mimetypes
import os
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crm_store import CRMStore
from metrics_store import MetricsStore
from twilio_calls import TokenIndex, TwilioDialer

APP_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(APP_DIR, "static")
CRM_PATH = os.path.join(APP_DIR, "crm_data.json")
METRICS_PATH = os.path.join(APP_DIR, "metrics.json")
ENV_PATH = os.path.join(APP_DIR, ".env")
APP_HOST = "127.0.0.1"
APP_PORT = 8000
HOOK_HOST = "127.0.0.1"
HOOK_PORT = 8765
MAX_BODY = 12 * 1024 * 1024


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


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


PUBLIC_API_PATHS = {"/api/health", "/api/auth/config"}


def make_app_handler(runtime):
    class AppHandler(BaseHTTPRequestHandler):
        def open_account(self, path):
            google = bool(runtime.client and runtime.client.anon_key)
            if not google or path in PUBLIC_API_PATHS or not path.startswith("/api/"):
                self.account = runtime.local
                return True
            header = self.headers.get("Authorization", "")
            token = header[7:].strip() if header.lower().startswith("bearer ") else ""
            user = runtime.client.auth_user(token)
            if not user:
                self.send_json(401, {"error": "Sign in with Google to continue."})
                return False
            self.account = runtime.session_for(user)
            return True

        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path == "/api/auth/config":
                client = runtime.client
                google = bool(client and client.anon_key)
                self.send_json(200, {
                    "google": google,
                    "url": client.project_url if google else "",
                    "anonKey": client.anon_key if google else "",
                })
                return
            if path == "/api/health":
                payload = runtime.health()
                self.send_json(200 if payload.get("ok") else 503, payload)
                return
            if path in ("/", "/index.html", "/static/", "/static/index.html"):
                self.send_file("index.html")
                return
            if path in ("/app.css", "/app.js", "/static/app.css", "/static/app.js"):
                self.send_file(os.path.basename(path))
                return
            if not self.open_account(path):
                return
            if path == "/api/auth/me":
                user = self.account.dialer if self.account else None
                email = getattr(user, "account_email", "") if user else ""
                user_id = getattr(user, "account_user_id", "") if user else ""
                self.send_json(200, {"id": user_id or "", "email": email or ""})
                return
            account = self.account
            if account is None:
                self.send_json(401, {"error": "Sign in with Google to continue."})
                return
            crm, dialer, metrics = account.crm, account.dialer, account.metrics
            if path.startswith("/api/") and path not in ("/api/state", "/api/live", "/api/metrics", "/api/health"):
                dialer.record_activity(f"GET {path}", "web")
            if path == "/api/state":
                try:
                    self.send_json(200, dialer.public_state())
                except OSError as exc:
                    self.report_storage_error(exc)
            elif path == "/api/live":
                try:
                    self.send_json(200, dialer.live_state())
                except OSError as exc:
                    self.report_storage_error(exc)
            elif path == "/api/metrics":
                try:
                    self.send_json(200, metrics.snapshot())
                except OSError as exc:
                    self.report_storage_error(exc)
            elif path == "/api/settings":
                runtime.reload_settings(dialer)
                self.send_json(200, dialer.settings_state())
            elif path == "/api/voice-token":
                try:
                    self.send_json(200, {"token": dialer.voice_access_token()})
                except ValueError as exc:
                    self.send_json(400, {"error": str(exc)})
            elif path == "/api/export.csv":
                try:
                    content = crm.csv_bytes()
                    self.send_bytes(200, content, "text/csv; charset=utf-8", {
                        "Content-Disposition": "attachment; filename=crm-export.csv",
                    })
                except OSError as exc:
                    self.report_storage_error(exc)
            else:
                self.send_json(404, {"error": "Not found"})

        def report_storage_error(self, exc):
            account = getattr(self, "account", None)
            if account:
                account.dialer.record_activity(f"Storage request failed: {exc}", "error")
            self.send_json(502, {"error": f"Could not read persistent data: {exc}"})

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            if not self.open_account(path):
                return
            account = self.account
            if account is None:
                self.send_json(401, {"error": "Sign in with Google to continue."})
                return
            crm, dialer = account.crm, account.dialer
            if path.startswith("/api/"):
                dialer.record_activity(f"POST {path}", "web")
            try:
                body = self.read_body()
                if path == "/api/import":
                    result = crm.add_csv(body)
                    try:
                        state = dialer.public_state()
                    except Exception as exc:
                        dialer.record_activity(f"Imported CSV but could not refresh state: {exc}", "error")
                        state = {"leads": crm.snapshot()}
                    self.send_json(200, {"import": result, "state": state})
                elif path == "/api/settings":
                    dialer.save_settings(self.read_json(body))
                    runtime.persist_settings(dialer)
                    self.send_json(200, dialer.settings_state())
                elif path == "/api/timezone":
                    result = dialer.set_timezone_filter(self.read_json(body).get("timezone"))
                    self.send_json(200, result)
                elif path == "/api/start":
                    self.send_json(200, dialer.start())
                elif path == "/api/pause":
                    self.send_json(200, dialer.pause())
                elif path == "/api/stop":
                    self.send_json(200, dialer.stop())
                elif path == "/api/hangup":
                    self.send_json(200, dialer.hangup_active())
                elif path == "/api/skip":
                    self.send_json(200, dialer.skip_active())
                elif path == "/api/enter-live":
                    self.send_json(200, dialer.enter_live_line())
                elif path == "/api/advance":
                    self.send_json(200, dialer.advance_now())
                elif path.startswith("/api/leads/") and path.endswith("/status"):
                    lead_id = urllib.parse.unquote(path.removeprefix("/api/leads/").removesuffix("/status"))
                    data = self.read_json(body)
                    lead = dialer.update_status(
                        lead_id, data.get("status"), data.get("scheduled_until"),
                        data.get("disposition"),
                    )
                    self.send_json(200, {"lead": lead, "state": dialer.public_state()})
                else:
                    self.send_json(404, {"error": "Not found"})
            except (ValueError, KeyError, UnicodeDecodeError) as exc:
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request rejected: {exc}", "error")
                self.send_json(400, {"error": str(exc)})
            except OSError as exc:
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request failed: {exc}", "error")
                self.send_json(500, {"error": f"Could not persist data: {exc}"})
            except Exception as exc:
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request failed: {exc}", "error")
                self.send_json(502, {"error": str(exc)})

        def do_DELETE(self):
            path = urllib.parse.urlsplit(self.path).path
            if not self.open_account(path):
                return
            account = self.account
            if account is None:
                self.send_json(401, {"error": "Sign in with Google to continue."})
                return
            crm, dialer = account.crm, account.dialer
            if path.startswith("/api/leads/"):
                lead_id = urllib.parse.unquote(path.removeprefix("/api/leads/"))
                try:
                    crm.remove(lead_id)
                    self.send_json(200, dialer.public_state())
                except KeyError as exc:
                    self.send_json(404, {"error": str(exc)})
                except OSError as exc:
                    self.send_json(500, {"error": f"Could not persist data: {exc}"})
            else:
                self.send_json(404, {"error": "Not found"})

        def read_body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                raise ValueError("Upload is too large (12 MB maximum).")
            return self.rfile.read(length)

        @staticmethod
        def read_json(body):
            if not body:
                return {}
            result = json.loads(body.decode("utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object.")
            return result

        def send_file(self, filename):
            full_path = os.path.join(STATIC_DIR, filename)
            try:
                with open(full_path, "rb") as source:
                    body = source.read()
            except OSError:
                self.send_json(404, {"error": "File not found"})
                return
            content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            if filename.endswith((".css", ".js", ".html")):
                content_type += "; charset=utf-8"
            self.send_bytes(200, body, content_type)

        def send_json(self, status, data):
            self.send_bytes(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                            "application/json; charset=utf-8")

        def send_bytes(self, status, body, content_type, headers=None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return AppHandler


def make_hook_handler(runtime):
    class HookHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.dispatch()

        def do_POST(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 256 * 1024:
                self.send_response(413)
                self.end_headers()
                return
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            values = urllib.parse.parse_qs(body, keep_blank_values=True)
            self.dispatch(values)

        def resolve_dialer(self, params, parts):
            token = params.get("CallToken") if urllib.parse.urlsplit(self.path).path == "/hooks/voice" else None
            if not token and len(parts) == 3 and parts[0] == "hooks":
                token = parts[1]
            dialer = runtime.tokens.lookup(token)
            if dialer is None and runtime.local:
                dialer = runtime.local.dialer
            return dialer

        def dispatch(self, body_values=None):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            params = {key: vals[-1] for key, vals in query.items()}
            params.update({key: vals[-1] for key, vals in (body_values or {}).items()})
            parts = parsed.path.strip("/").split("/")
            dialer = self.resolve_dialer(params, parts)
            if dialer is None:
                status, content_type, content = 404, "text/plain", "Unknown call"
            else:
                callback_url = dialer.public_base_url + self.path
                valid = dialer.validate_webhook(
                    callback_url,
                    self.headers.get("X-Twilio-Signature", ""),
                    body_values or {},
                )
                if not valid:
                    dialer.record_activity("Rejected unsigned Twilio callback", "error")
                    status, content_type, content = 403, "text/plain", "Invalid Twilio signature"
                else:
                    dialer.record_activity(f"Twilio callback: {parts[-1] if parts else 'unknown'}", "webhook")
                    if parsed.path == "/hooks/voice":
                        status, content_type, content = dialer.handle_client_voice(params)
                    elif len(parts) == 3 and parts[0] == "hooks":
                        status, content_type, content = dialer.handle_webhook(parts[1], parts[2], params)
                    else:
                        status, content_type, content = 404, "text/plain", "Not found"
            body = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    return HookHandler


def serve():
    runtime = AppRuntime().configure(migrate=True)
    app_server = QuietThreadingHTTPServer(
        (APP_HOST, APP_PORT),
        make_app_handler(runtime),
    )
    hook_server = QuietThreadingHTTPServer((HOOK_HOST, HOOK_PORT), make_hook_handler(runtime))
    threading.Thread(target=hook_server.serve_forever, name="twilio-callback-server", daemon=True).start()
    print(f"CRM web app: http://{APP_HOST}:{APP_PORT}")
    print(f"Persistent storage: {runtime.storage_name}")
    print(f"Twilio callback server: http://{HOOK_HOST}:{HOOK_PORT} (expose this port with HTTPS)")
    try:
        app_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        accounts = []
        if runtime.local:
            accounts.append(runtime.local)
        accounts.extend(runtime.sessions.values())
        for account in accounts:
            account.dialer.stop()
        app_server.shutdown()
        hook_server.shutdown()
        app_server.server_close()
        hook_server.server_close()


if __name__ == "__main__":
    serve()