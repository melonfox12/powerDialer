import traceback

from shared.infra import debug_event

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
                from features.dialer import post_timezone

                post_timezone(self, self.read_json(body))
            elif path == "/api/start":
                from features.dialer import post_start

                post_start(self)
            elif path == "/api/pause":
                from features.dialer import post_pause

                post_pause(self)
            elif path == "/api/stop":
                from features.dialer import post_stop

                post_stop(self)
            elif path == "/api/hangup":
                from features.dialer import post_hangup

                post_hangup(self)
            elif path == "/api/skip":
                from features.dialer import post_skip

                post_skip(self)
            elif path == "/api/advance":
                from features.dialer import post_advance

                post_advance(self)
            elif path.startswith("/api/leads/") and path.endswith("/dial"):
                from features.dialer import post_dial

                post_dial(self)
            elif path.startswith("/api/leads/") and path.endswith("/status"):
                from features.dialer import post_status

                post_status(self, self.read_json(body))
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
