"""In-process app and hook servers pointed at a temporary local-JSON store."""

import os
import threading
import urllib.error
import urllib.request

from routes.hooks import make_hook_handler
from features.accounts import AppRuntime
from routes.ui import make_app_handler
from server import QuietThreadingHTTPServer

_ISOLATED = (
    "SUPABASE_URL",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_ANON_KEY",
    "SUPABASE_PUBLISHABLE_KEY",
)


class LocalServers:
    def __init__(self, directory):
        self.directory = directory
        self._saved_env = {}
        self.runtime = None
        self.app_server = None
        self.hook_server = None
        self._threads = []

    def start(self):
        import features.accounts as runtime_module

        for key in _ISOLATED:
            if key in os.environ:
                self._saved_env[key] = os.environ.pop(key)
        self._runtime_module = runtime_module
        self._saved_paths = (
            runtime_module.ENV_PATH,
            runtime_module.CRM_PATH,
            runtime_module.METRICS_PATH,
        )
        runtime_module.ENV_PATH = os.path.join(self.directory, ".env")
        runtime_module.CRM_PATH = os.path.join(self.directory, "crm.json")
        runtime_module.METRICS_PATH = os.path.join(self.directory, "metrics.json")
        self.runtime = AppRuntime().configure()
        self.app_server = QuietThreadingHTTPServer(("127.0.0.1", 0), make_app_handler(self.runtime))
        self.hook_server = QuietThreadingHTTPServer(("127.0.0.1", 0), make_hook_handler(self.runtime))
        for server in (self.app_server, self.hook_server):
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._threads.append(thread)
        app_port = self.app_server.server_address[1]
        hook_port = self.hook_server.server_address[1]
        self.app_base = f"http://127.0.0.1:{app_port}"
        self.hook_base = f"http://127.0.0.1:{hook_port}"
        return self

    def stop(self):
        for server in (self.app_server, self.hook_server):
            if server is not None:
                server.shutdown()
                server.server_close()
        for thread in self._threads:
            thread.join(timeout=2)
        if self.runtime is not None:
            import features.accounts as runtime_module

            runtime_module.ENV_PATH, runtime_module.CRM_PATH, runtime_module.METRICS_PATH = self._saved_paths
        os.environ.update(self._saved_env)
        self._saved_env = {}

    def request(self, base, method, path, body=None, headers=None):
        data = body if isinstance(body, bytes) else (None if body is None else body.encode("utf-8"))
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as response:
                return response.status, response.read(), response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), exc.headers.get("Content-Type", "")
