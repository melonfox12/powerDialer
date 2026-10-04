"""Local web application and public Twilio callback servers."""

import threading
from http.server import ThreadingHTTPServer

from routes.hooks import make_hook_handler
from routes.runtime import APP_HOST, APP_PORT, HOOK_HOST, HOOK_PORT, AppRuntime
from routes.ui import make_app_handler


class QuietThreadingHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def serve():
    from core.debug_log import enable

    enable()
    runtime = AppRuntime().configure(migrate=True)
    app_server = QuietThreadingHTTPServer(
        (APP_HOST, APP_PORT),
        make_app_handler(runtime),
    )
    hook_server = QuietThreadingHTTPServer((HOOK_HOST, HOOK_PORT), make_hook_handler(runtime))
    threading.Thread(target=hook_server.serve_forever, name="twilio-callback-server", daemon=True).start()
    print(f"CRM web app: http://{APP_HOST}:{APP_PORT}", flush=True)
    print(f"Persistent storage: {runtime.storage_name}", flush=True)
    print(f"Twilio callback server: http://{HOOK_HOST}:{HOOK_PORT} (expose this port with HTTPS)", flush=True)
    print("Debug log: debug-session.log (clicks, requests, dialer events, errors)", flush=True)
    try:
        app_server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        accounts = []
        if runtime.local:
            accounts.append(runtime.local)
        accounts.extend(runtime.sessions.values())
        for account in accounts:
            account.dialer.stop()
        app_server.shutdown()
        hook_server.shutdown()
        app_server.server_close()
        hook_server.server_close()


if __name__ == "__main__":
    serve()
