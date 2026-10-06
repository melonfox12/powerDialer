import json

from features.accounts import resolve_account
from shared.infra import debug_event

class AccountMixin:
    def open_account(self, path):
        account, error = resolve_account(self.runtime, path, self.headers.get("Authorization", ""))
        if error:
            self.send_json(401, error)
            return False
        self.account = account
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

    def report_storage_error(self, exc):
        self._trace_error = str(exc)
        account = getattr(self, "account", None)
        if account:
            account.dialer.record_activity(f"Storage request failed: {exc}", "error")
        self.send_json(502, {"error": f"Could not read persistent data: {exc}"})
