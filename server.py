"""Local web application and public Twilio callback servers."""

import json
import mimetypes
import os
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from crm_store import CRMStore
from metrics_store import MetricsStore
from twilio_calls import TwilioDialer

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


def make_app_handler(crm, dialer, metrics, storage_name="local JSON files"):
    class AppHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith("/api/") and path not in ("/api/state", "/api/metrics", "/api/health"):
                dialer.record_activity(f"GET {path}", "web")
            if path == "/api/state":
                try:
                    self.send_json(200, dialer.public_state())
                except OSError as exc:
                    self.report_storage_error(exc)
            elif path == "/api/metrics":
                try:
                    self.send_json(200, metrics.snapshot())
                except OSError as exc:
                    self.report_storage_error(exc)
            elif path == "/api/settings":
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
            elif path in ("/", "/index.html", "/static/", "/static/index.html"):
                self.send_file("index.html")
            elif path in ("/app.css", "/app.js", "/static/app.css", "/static/app.js"):
                self.send_file(os.path.basename(path))
            elif path == "/api/health":
                try:
                    crm.snapshot()
                    metrics.snapshot()
                    self.send_json(200, {"ok": True, "storage": storage_name})
                except OSError as exc:
                    self.send_json(503, {
                        "ok": False,
                        "storage": storage_name,
                        "error": str(exc),
                    })
            else:
                self.send_json(404, {"error": "Not found"})

        def report_storage_error(self, exc):
            dialer.record_activity(f"Storage request failed: {exc}", "error")
            self.send_json(502, {"error": f"Could not read persistent data: {exc}"})

        def do_POST(self):
            path = urllib.parse.urlsplit(self.path).path
            if path.startswith("/api/"):
                dialer.record_activity(f"POST {path}", "web")
            try:
                body = self.read_body()
                if path == "/api/import":
                    result = crm.add_csv(body)
                    self.send_json(200, {"import": result, "state": dialer.public_state()})
                elif path == "/api/settings":
                    result = dialer.save_settings(self.read_json(body))
                    self.send_json(200, result)
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
                elif path.startswith("/api/leads/") and path.endswith("/status"):
                    lead_id = urllib.parse.unquote(path.removeprefix("/api/leads/").removesuffix("/status"))
                    data = self.read_json(body)
                    lead = dialer.update_status(lead_id, data.get("status", ""))
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


def make_hook_handler(dialer):
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

        def dispatch(self, body_values=None):
            parsed = urllib.parse.urlsplit(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            params = {key: vals[-1] for key, vals in query.items()}
            params.update({key: vals[-1] for key, vals in (body_values or {}).items()})
            parts = parsed.path.strip("/").split("/")
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
    from supabase_store import SupabaseCRMStore, SupabaseMetricsStore, SupabaseClient
    from twilio_calls import read_env

    values = read_env(ENV_PATH)
    client = SupabaseClient.from_env(values)
    if client:
        crm = SupabaseCRMStore(client)
        metrics = SupabaseMetricsStore(client)
        crm.snapshot()
        metrics.snapshot()
        storage_name = "Supabase"
    else:
        crm = CRMStore(CRM_PATH)
        metrics = MetricsStore(METRICS_PATH)
        storage_name = "local JSON files"
    dialer = TwilioDialer(crm, ENV_PATH, metrics=metrics)
    app_server = QuietThreadingHTTPServer(
        (APP_HOST, APP_PORT),
        make_app_handler(crm, dialer, metrics, storage_name),
    )
    hook_server = QuietThreadingHTTPServer((HOOK_HOST, HOOK_PORT), make_hook_handler(dialer))
    threading.Thread(target=hook_server.serve_forever, name="twilio-callback-server", daemon=True).start()
    print(f"CRM web app: http://{APP_HOST}:{APP_PORT}")
    print(f"Persistent storage: {storage_name}")
    print(f"Twilio callback server: http://{HOOK_HOST}:{HOOK_PORT} (expose this port with HTTPS)")
    try:
        app_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        dialer.stop()
        app_server.shutdown()
        hook_server.shutdown()
        app_server.server_close()
        hook_server.server_close()


if __name__ == "__main__":
    serve()