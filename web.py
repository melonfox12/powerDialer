"""HTTP glue: tracing, static files, page assembly, and the route table."""

import json
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

from _web.respond import HandlerMixin
from features import dialer, metrics, prospects, settings
from features.accounts import resolve_account
from shared.infra import debug_event



def get_auth_config(request):
    client = request.runtime.client
    google = bool(client and client.anon_key)
    request.send_json(200, {
        "google": google,
        "url": client.project_url if google else "",
        "anonKey": client.anon_key if google else "",
    })


def get_health(request):
    payload = request.runtime.health()
    request.send_json(200 if payload.get("ok") else 503, payload)


def get_auth_me(request):
    user = request.account.dialer if request.account else None
    email = getattr(user, "account_email", "") if user else ""
    user_id = getattr(user, "account_user_id", "") if user else ""
    request.send_json(200, {"id": user_id or "", "email": email or ""})


def ingest_client_debug(request):
    length = int(request.headers.get("Content-Length", "0") or 0)
    if length > 8192:
        request.send_response(413)
        request.send_header("Content-Length", "0")
        request.end_headers()
        return
    raw = request.rfile.read(length) if length else b""
    try:
        data = json.loads(raw.decode("utf-8")) if raw else {}
    except (UnicodeDecodeError, json.JSONDecodeError):
        data = None
    if not isinstance(data, dict) or not str(data.get("message") or "").strip():
        request.send_response(400)
        request.send_header("Content-Length", "0")
        request.end_headers()
        return
    debug_event(str(data.get("level") or "client")[:24], data.get("message"), data.get("detail") or "")
    request.send_response(204)
    request.send_header("Content-Length", "0")
    request.send_header("Cache-Control", "no-store")
    request.end_headers()


SYSTEM_ROUTES = [
    ("GET", "/api/auth/config", get_auth_config, "none"),
    ("GET", "/api/health", get_health, "none"),
    ("GET", "/api/auth/me", get_auth_me, "none"),
    ("POST", "/api/debug", ingest_client_debug, "debug"),
]

FEATURE_ROUTES = (
    settings.ROUTES + metrics.ROUTES + prospects.ROUTES + dialer.ROUTES
)


def all_routes():
    return SYSTEM_ROUTES + FEATURE_ROUTES


def match_route(method, path):
    for route_method, pattern, handler, profile in all_routes():
        if route_method != method:
            continue
        params = _match_pattern(pattern, path)
        if params is not None:
            return handler, profile, params
    return None


def _match_pattern(pattern, path):
    if "{" not in pattern:
        return {} if pattern == path else None
    pattern_parts = pattern.split("/")
    path_parts = path.split("/")
    if pattern == "/api/leads/{id}" and path.startswith("/api/leads/"):
        return {"id": urllib.parse.unquote(path[len("/api/leads/"):])}
    if len(pattern_parts) != len(path_parts):
        return None
    params = {}
    for expected, found in zip(pattern_parts, path_parts):
        if expected.startswith("{") and expected.endswith("}"):
            params[expected[1:-1]] = urllib.parse.unquote(found)
        elif expected != found:
            return None
    return params


UPLOAD_CONTENT_TYPES = ("application/octet-stream", "text/csv")


def request_refusal(method, path, headers, port):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    if str(headers.get("Host") or "").strip().lower() not in hosts:
        return 403, "Unexpected Host header."
    if method not in ("POST", "DELETE"):
        return None
    origin = headers.get("Origin")
    if origin is not None and origin.strip().lower() not in {f"http://{host}" for host in hosts}:
        return 403, "Cross-origin request refused."
    if method == "POST":
        found = match_route("POST", path)
        upload = found is not None and found[0] is prospects.post_import
        allowed = UPLOAD_CONTENT_TYPES if upload else ("application/json",)
        if not str(headers.get("Content-Type") or "").strip().lower().startswith(allowed):
            return 415, f"Content-Type must be {' or '.join(allowed)}."
    return None


class AppHandler(HandlerMixin, BaseHTTPRequestHandler):
    def refuse_untrusted(self):
        refusal = request_refusal(self.command, self._trace_path, self.headers, self.server.server_address[1])
        if refusal is None:
            return False
        status, message = refusal
        self._trace_error = message
        self.send_json(status, {"error": message})
        return True

    def open_account(self, path):
        account, error = resolve_account(self.runtime, path, self.headers.get("Authorization", ""))
        if error:
            self.send_json(401, error)
            return False
        self.account = account
        self.ctx = FeatureContext(self)
        return True

    def report_storage_error(self, exc):
        self._trace_error = str(exc)
        account = getattr(self, "account", None)
        if account:
            account.dialer.record_activity(f"Storage request failed: {exc}", "error")
        self.send_json(502, {"error": f"Could not read persistent data: {exc}"})

    def do_GET(self):
        self.begin_trace()
        path = self._trace_path
        if self.refuse_untrusted():
            return
        if path == "/api/auth/config":
            get_auth_config(self)
            return
        if path == "/api/health":
            get_health(self)
            return
        if self.serve_static(path):
            return
        if not self.open_account(path):
            return
        if path == "/api/auth/me":
            get_auth_me(self)
            return
        account = self.account
        if account is None:
            self.send_json(401, {"error": "Sign in with Google to continue."})
            return
        dialer_session = account.dialer
        if path.startswith("/api/") and path not in ("/api/state", "/api/live", "/api/metrics", "/api/health"):
            dialer_session.record_activity(f"GET {path}", "web")
        found = match_route("GET", path)
        if found is None:
            self.send_json(404, {"error": "Not found"})
            return
        handler, profile, _params = found
        if profile == "voice-token":
            try:
                handler(self)
            except ValueError as exc:
                self._trace_error = str(exc)
                self.send_json(400, {"error": str(exc)})
            return
        if profile == "GET reads":
            try:
                handler(self)
            except OSError as exc:
                self.report_storage_error(exc)
            return
        handler(self)

    def do_POST(self):
        self.begin_trace()
        path = self._trace_path
        if self.refuse_untrusted():
            return
        if path == "/api/debug":
            ingest_client_debug(self)
            return
        if not self.open_account(path):
            return
        account = self.account
        if account is None:
            self.send_json(401, {"error": "Sign in with Google to continue."})
            return
        dialer_session = account.dialer
        if path.startswith("/api/"):
            dialer_session.record_activity(f"POST {path}", "web")
        try:
            body = self.read_body()
            found = match_route("POST", path)
            if found is None:
                self.send_json(404, {"error": "Not found"})
                return
            handler, _profile, _params = found
            if handler in (prospects.post_lead, settings.post_settings, dialer.post_timezone, dialer.post_status):
                handler(self, self.read_json(body))
            elif handler is prospects.post_import:
                handler(self, body)
            else:
                handler(self)
        except (ValueError, KeyError, UnicodeDecodeError) as exc:
            self._trace_error = str(exc)
            if path.startswith("/api/"):
                dialer_session.record_activity(f"Request rejected: {exc}", "error")
            self.send_json(400, {"error": str(exc)})
        except OSError as exc:
            self._trace_error = str(exc)
            if path.startswith("/api/"):
                dialer_session.record_activity(f"Request failed: {exc}", "error")
            self.send_json(500, {"error": f"Could not persist data: {exc}"})
        except Exception as exc:
            self._trace_error = str(exc)
            debug_event("error", f"POST {path}", traceback.format_exc())
            if path.startswith("/api/"):
                dialer_session.record_activity(f"Request failed: {exc}", "error")
            self.send_json(502, {"error": str(exc)})

    def do_DELETE(self):
        self.begin_trace()
        path = self._trace_path
        if self.refuse_untrusted():
            return
        if not self.open_account(path):
            return
        account = self.account
        if account is None:
            self.send_json(401, {"error": "Sign in with Google to continue."})
            return
        if path.startswith("/api/leads/"):
            prospects.delete_lead(self)
        else:
            self.send_json(404, {"error": "Not found"})


class FeatureContext:
    def __init__(self, request):
        self.request = request

    def state(self):
        return self.request.account.dialer.public_state()

    def log(self, message, source):
        self.request.account.dialer.record_activity(message, source)

    def reload_settings(self):
        self.request.runtime.reload_settings(self.request.account.dialer)

    def save_posted_settings(self, data):
        session = self.request.account.dialer
        session.save_settings(data)

    def settings_view(self):
        return self.request.account.dialer.settings_state()


def make_app_handler(runtime):
    AppHandler.runtime = runtime
    return AppHandler
