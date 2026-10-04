"""Twilio callback routes on port 8765."""

import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler

from debug_log import debug_event
from routes.http import HandlerMixin, log_server_fault


def make_hook_handler(runtime):
    class HookHandler(HandlerMixin, BaseHTTPRequestHandler):
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
            started = time.perf_counter()
            try:
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
            except Exception:
                debug_event("error", f"hook {parsed.path}", traceback.format_exc())
                status, content_type, content = 500, "text/plain", "Callback failed"
            elapsed = int((time.perf_counter() - started) * 1000)
            summary = " ".join(
                f"{key}={params.get(key)}"
                for key in ("CallStatus", "DialCallStatus", "AnsweredBy", "ErrorCode")
                if params.get(key)
            )
            debug_event("hook", f"{self.command} {parsed.path} -> {status} {elapsed}ms", summary)
            body = content.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_error(self, format, *args):
            log_server_fault(format, *args)

        def log_message(self, format, *args):
            return

    return HookHandler
