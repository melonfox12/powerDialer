"""Response helpers shared by the app server and the Twilio hook server."""

import json
import mimetypes
import os
import time
import traceback
import urllib.parse

from shared.config import MAX_BODY, QUIET_HTTP, STATIC_DIR
from shared.infra import debug_event
from shared.vocabulary import vocabulary_json

def log_server_fault(format, *args):
    detail = traceback.format_exc()
    if detail.strip() in ("NoneType: None", "None"):
        detail = (format % args) if args else str(format)
    debug_event("error", "uncaught", detail)


class HandlerMixin:
        def begin_trace(self):
            self._trace_t0 = time.perf_counter()
            self._trace_path = urllib.parse.urlsplit(self.path).path
            self._trace_logged = False
            self._trace_error = ""

        def finish_trace(self, status):
            if getattr(self, "_trace_logged", False):
                return
            self._trace_logged = True
            path = getattr(self, "_trace_path", urllib.parse.urlsplit(self.path).path)
            error = getattr(self, "_trace_error", "")
            quiet = path in QUIET_HTTP or path.startswith(("/css/", "/js/", "/static/css/", "/static/js/"))
            if quiet and status < 500 and not error:
                return
            elapsed = int((time.perf_counter() - getattr(self, "_trace_t0", time.perf_counter())) * 1000)
            detail = f"{status} {elapsed}ms"
            if error:
                detail += f" {error}"
            debug_event("http", f"{self.command} {path}", detail)

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

        def send_app_page(self):
            parts = (
                os.path.join(STATIC_DIR, "app-shell", "chrome.html"),
                os.path.join(STATIC_DIR, "app-shell", "dialer.html"),
                os.path.join(STATIC_DIR, "app-shell", "metrics.html"),
                os.path.join(STATIC_DIR, "app-shell", "dialogs.html"),
            )
            try:
                chunks = []
                for part in parts:
                    with open(part, "rb") as source:
                        chunks.append(source.read())
                body = b"".join(chunks)
                script = (
                    b'<script type="application/json" id="vocabulary">'
                    + vocabulary_json().encode("utf-8")
                    + b"</script>"
                )
                body = body.replace(b"</head>", script + b"</head>", 1)
            except OSError:
                self.send_json(404, {"error": "File not found"})
                return
            self.send_bytes(200, body, "text/html; charset=utf-8")

        def send_file(self, filename):
            full_path = os.path.join(STATIC_DIR, filename)
            try:
                with open(full_path, "rb") as source:
                    body = source.read()
            except OSError:
                self.send_json(404, {"error": "File not found"})
                return
            if filename.endswith(".js"):
                content_type = "text/javascript"
            elif filename.endswith(".css"):
                content_type = "text/css"
            elif filename.endswith(".html"):
                content_type = "text/html"
            else:
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
            self.finish_trace(status)

        def log_error(self, format, *args):
            log_server_fault(format, *args)

        def log_message(self, format, *args):
            return

        def serve_static(self, path):
            if path in ("/", "/index.html", "/static/", "/static/index.html"):
                self.send_app_page()
                return True
            rel = path[len("/static/"):] if path.startswith("/static/") else path.lstrip("/")
            if not rel or rel.endswith("/") or "\\" in rel or ".." in rel.split("/"):
                return False
            root = os.path.normpath(STATIC_DIR)
            full = os.path.normpath(os.path.join(root, rel))
            if full != root and not full.startswith(root + os.sep):
                return False
            if not os.path.isfile(full):
                return False
            self.send_file(rel)
            return True

