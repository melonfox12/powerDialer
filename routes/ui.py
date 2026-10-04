"""Browser UI routes on port 8000."""

import json
import os
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

from debug_log import debug_event
from routes.http import HandlerMixin, log_server_fault
from routes.runtime import PUBLIC_API_PATHS

def make_app_handler(runtime):
    class AppHandler(HandlerMixin, BaseHTTPRequestHandler):
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

        def ingest_client_debug(self):
            length = int(self.headers.get("Content-Length", "0") or 0)
            if length > 8192:
                self.send_response(413)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            raw = self.rfile.read(length) if length else b""
            try:
                data = json.loads(raw.decode("utf-8")) if raw else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                data = None
            if not isinstance(data, dict) or not str(data.get("message") or "").strip():
                self.send_response(400)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            debug_event(str(data.get("level") or "client")[:24], data.get("message"), data.get("detail") or "")
            self.send_response(204)
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def do_GET(self):
            self.begin_trace()
            path = self._trace_path
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
            if self.serve_static(path):
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
                    self._trace_error = str(exc)
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
            self._trace_error = str(exc)
            account = getattr(self, "account", None)
            if account:
                account.dialer.record_activity(f"Storage request failed: {exc}", "error")
            self.send_json(502, {"error": f"Could not read persistent data: {exc}"})

        def do_POST(self):
            self.begin_trace()
            path = self._trace_path
            if path == "/api/debug":
                self.ingest_client_debug()
                return
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
                self._trace_error = str(exc)
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request rejected: {exc}", "error")
                self.send_json(400, {"error": str(exc)})
            except OSError as exc:
                self._trace_error = str(exc)
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request failed: {exc}", "error")
                self.send_json(500, {"error": f"Could not persist data: {exc}"})
            except Exception as exc:
                self._trace_error = str(exc)
                debug_event("error", f"POST {path}", traceback.format_exc())
                if path.startswith("/api/"):
                    dialer.record_activity(f"Request failed: {exc}", "error")
                self.send_json(502, {"error": str(exc)})

        def do_DELETE(self):
            self.begin_trace()
            path = self._trace_path
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
                    self._trace_error = str(exc)
                    self.send_json(404, {"error": str(exc)})
                except OSError as exc:
                    self._trace_error = str(exc)
                    self.send_json(500, {"error": f"Could not persist data: {exc}"})
            else:
                self.send_json(404, {"error": "Not found"})

    return AppHandler

