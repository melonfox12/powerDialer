class ReadMixin:
    def do_GET(self):
        self.begin_trace()
        path = self._trace_path
        if path == "/api/auth/config":
            client = self.runtime.client
            google = bool(client and client.anon_key)
            self.send_json(200, {
                "google": google,
                "url": client.project_url if google else "",
                "anonKey": client.anon_key if google else "",
            })
            return
        if path == "/api/health":
            payload = self.runtime.health()
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
        dialer = account.dialer
        if path.startswith("/api/") and path not in ("/api/state", "/api/live", "/api/metrics", "/api/health"):
            dialer.record_activity(f"GET {path}", "web")
        if path == "/api/state":
            from features.dialer import get_state

            get_state(self)
        elif path == "/api/live":
            from features.dialer import get_live

            get_live(self)
        elif path == "/api/metrics":
            from features.metrics import get_metrics

            get_metrics(self)
        elif path == "/api/settings":
            from features.settings import get_settings

            get_settings(self)
        elif path == "/api/voice-token":
            from features.dialer import get_voice_token

            get_voice_token(self)
        elif path == "/api/export.csv":
            from features.prospects import get_export

            get_export(self)
        else:
            self.send_json(404, {"error": "Not found"})
