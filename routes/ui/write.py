import traceback
import urllib.parse
from core.debug_log import debug_event

class WriteMixin:
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
        dialer = account.dialer
        if path.startswith("/api/"):
            dialer.record_activity(f"POST {path}", "web")
        try:
            body = self.read_body()
            if path == "/api/leads":
                from features.prospects import post_lead

                post_lead(self, self.read_json(body))
            elif path == "/api/import":
                from features.prospects import post_import

                post_import(self, body)
            elif path == "/api/settings":
                from features.settings import post_settings

                post_settings(self, self.read_json(body))
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
            elif path == "/api/advance":
                self.send_json(200, dialer.advance_now())
            elif path.startswith("/api/leads/") and path.endswith("/dial"):
                lead_id = urllib.parse.unquote(path.removeprefix("/api/leads/").removesuffix("/dial"))
                self.send_json(200, dialer.dial_lead(lead_id))
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
        if path.startswith("/api/leads/"):
            from features.prospects import delete_lead

            delete_lead(self)
        else:
            self.send_json(404, {"error": "Not found"})
