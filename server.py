# -----------------------------------------------------------------------------
# File: server.py
# Purpose: Process entry — configure AppRuntime, start CRM HTTP + Twilio hook servers.
# Exports: QuietThreadingHTTPServer, serve.
# Invoked by: dialer.py __main__, tests via serve() or handlers.
# Depends on: _web.hooks, features.accounts.AppRuntime, shared.config, web.make_app_handler,
#             features.ai_media_bridge.maybe_start_embedded, shared.infra.enable
# -----------------------------------------------------------------------------
"""Local web application and public Twilio callback servers."""

import threading
from http.server import ThreadingHTTPServer

# Twilio-facing handler factory on HOOK_PORT.
from _web.hooks import make_hook_handler
# Builds Account(s), storage backend, and health check state.
from features.accounts import AppRuntime
from shared.config import APP_HOST, APP_PORT, HOOK_HOST, HOOK_PORT
# CRM + JSON API handler on APP_PORT.
from web import make_app_handler


# Thread-per-request HTTP server; daemon_threads avoids blocking shutdown on in-flight hooks.
class QuietThreadingHTTPServer(ThreadingHTTPServer):

    # Child request threads do not block process exit on Ctrl+C.
    daemon_threads = True
    # Allow quick restart during dev without "address already in use".
    allow_reuse_address = True


# Wire runtime, optional AI bridge, two HTTP servers; block until KeyboardInterrupt.
def serve():
    from shared.infra import enable

    # Turn on debug-session.log and related tracing hooks.
    enable()
    # Load .env, choose Supabase vs local JSON, create local Account if offline.
    runtime = AppRuntime().configure()
    from features.ai_media_bridge import maybe_start_embedded

    # Optionally spawn embedded WebSocket bridge for AI voice (AI_BRIDGE_EMBEDDED).
    maybe_start_embedded()
    # Main app: static files + /api/* on APP_HOST:APP_PORT.
    app_server = QuietThreadingHTTPServer(
        (APP_HOST, APP_PORT),
        make_app_handler(runtime),
    )
    # Twilio callbacks: separate port so tunnel can point Twilio at HOOK only if needed.
    hook_server = QuietThreadingHTTPServer((HOOK_HOST, HOOK_PORT), make_hook_handler(runtime))
    # Hook server runs in background thread; app server blocks the main thread.
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
        # Collect every live Dialer session (local + signed-in users) for graceful Twilio hangup.
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