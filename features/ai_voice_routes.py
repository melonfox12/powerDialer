"""HTTP surface for the Twilio media bridge (shared-secret auth)."""

import urllib.parse

from features import ai_voice_inbound, ai_voice_runtime


def _secret(request):
    return request.headers.get("X-AI-Bridge-Secret") or request.headers.get("x-ai-bridge-secret") or ""


def _query(request, key):
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.path).query)
    return (query.get(key) or [""])[-1]


def _dialer_for_request(runtime, session_id):
    accounts = []
    if runtime.local:
        accounts.append(runtime.local)
    accounts.extend(runtime.sessions.values())
    for account in accounts:
        dialer = account.dialer
        with dialer.lock:
            if session_id and session_id in dialer.ai_voice_sessions:
                return dialer
    for account in accounts:
        return account.dialer
    return None


def _require_bridge(request, dialer):
    if not ai_voice_runtime.bridge_secret_ok(dialer, _secret(request)):
        request.send_json(403, {"error": "Invalid bridge secret."})
        return False
    return True


def get_ai_voice_bootstrap(request):
    session_id = _query(request, "session") or _query(request, "session_id")
    dialer = _dialer_for_request(request.runtime, session_id)
    if dialer is None:
        request.send_json(404, {"error": "No dialer."})
        return
    if not _require_bridge(request, dialer):
        return
    payload = ai_voice_runtime.bootstrap(dialer, session_id)
    if not payload:
        request.send_json(404, {"error": "Unknown session."})
        return
    request.send_json(200, payload)


def get_ai_voice_stream_sync(request):
    session_id = _query(request, "session") or _query(request, "session_id")
    dialer = _dialer_for_request(request.runtime, session_id)
    if dialer is None:
        request.send_json(404, {"error": "No dialer."})
        return
    if not _require_bridge(request, dialer):
        return
    request.send_json(200, ai_voice_runtime.stream_sync(dialer, session_id))


def post_ai_voice_stream_started(request, data):
    session_id = str(data.get("session") or data.get("session_id") or "").strip()
    dialer = _dialer_for_request(request.runtime, session_id)
    if dialer is None:
        request.send_json(404, {"error": "No dialer."})
        return
    if not _require_bridge(request, dialer):
        return
    ai_voice_runtime.mark_stream_started(dialer, session_id)
    sync = ai_voice_runtime.stream_sync(dialer, session_id)
    request.send_json(200, {"ok": True, **sync})


def post_ai_voice_inbound(request, data):
    session_id = str(data.get("session") or data.get("session_id") or "").strip()
    dialer = _dialer_for_request(request.runtime, session_id)
    if dialer is None:
        request.send_json(404, {"error": "No dialer."})
        return
    if not _require_bridge(request, dialer):
        return
    payload = data.get("payload") or ""
    if payload:
        ai_voice_inbound.ingest_mulaw(dialer, session_id, payload)
    for item in data.get("payloads") or []:
        if item:
            ai_voice_inbound.ingest_mulaw(dialer, session_id, item)
    request.send_json(200, {"ok": True})


def post_ai_voice_stream_stopped(request, data):
    session_id = str(data.get("session") or data.get("session_id") or "").strip()
    dialer = _dialer_for_request(request.runtime, session_id)
    if dialer is None:
        request.send_json(404, {"error": "No dialer."})
        return
    if not _require_bridge(request, dialer):
        return
    ai_voice_runtime.end_session(dialer, session_id)
    request.send_json(200, {"ok": True})


ROUTES = [
    ("GET", "/api/ai-voice/bootstrap", get_ai_voice_bootstrap, "bridge"),
    ("GET", "/api/ai-voice/stream-sync", get_ai_voice_stream_sync, "bridge"),
    ("POST", "/api/ai-voice/stream-started", post_ai_voice_stream_started, "bridge"),
    ("POST", "/api/ai-voice/stream-stopped", post_ai_voice_stream_stopped, "bridge"),
    ("POST", "/api/ai-voice/inbound", post_ai_voice_inbound, "bridge"),
]
