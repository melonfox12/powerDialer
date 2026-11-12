"""Twilio Media Stream websocket bridge (inbound mulaw → dialer, outbound TTS ← dialer)."""

import asyncio
import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request

try:
    import websockets
except ImportError:
    websockets = None


def api_json(app_url, secret, method, path, payload=None):
    body = None
    headers = {"X-AI-Bridge-Secret": secret, "Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(f"{app_url.rstrip('/')}{path}", data=body, method=method, headers=headers)
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


async def poll_and_send(app_url, secret, session_id, stream_sid, ws):
    while True:
        await asyncio.sleep(0.12)
        try:
            data = api_json(
                app_url,
                secret,
                "GET",
                f"/api/ai-voice/stream-sync?session={urllib.parse.quote(session_id)}",
            )
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
            continue
        if data.get("ended"):
            break
        for chunk in data.get("chunks") or []:
            if not chunk or not stream_sid:
                continue
            await ws.send(json.dumps({
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": chunk},
            }))


async def twilio_handler(app_url, secret, ws, path=None):
    session_id = ""
    stream_sid = ""
    if path and "?" in path:
        query = urllib.parse.parse_qs(path.split("?", 1)[1])
        session_id = (query.get("session") or [""])[-1]
    poll_task = None
    inbound_batches = []
    inbound_task = None

    async def flush_inbound():
        while True:
            await asyncio.sleep(0.2)
            if not session_id or not inbound_batches:
                continue
            batch = inbound_batches[:]
            inbound_batches.clear()
            combined = b"".join(batch)
            if not combined:
                continue
            payload = base64.b64encode(combined).decode("ascii")
            try:
                api_json(app_url, secret, "POST", "/api/ai-voice/inbound", {"session_id": session_id, "payload": payload})
            except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
                pass

    async for message in ws:
        data = json.loads(message)
        event = data.get("event")
        if event == "start":
            stream_sid = (data.get("start") or {}).get("streamSid") or ""
            params = (data.get("start") or {}).get("customParameters") or {}
            session_id = session_id or params.get("session") or ""
            if session_id:
                try:
                    api_json(app_url, secret, "POST", "/api/ai-voice/stream-started", {"session_id": session_id})
                except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
                    pass
                poll_task = asyncio.create_task(poll_and_send(app_url, secret, session_id, stream_sid, ws))
                inbound_task = asyncio.create_task(flush_inbound())
        elif event == "media":
            payload = (data.get("media") or {}).get("payload") or ""
            if session_id and payload:
                try:
                    inbound_batches.append(base64.b64decode(payload))
                except (ValueError, TypeError):
                    pass
        elif event == "stop":
            if session_id:
                try:
                    api_json(app_url, secret, "POST", "/api/ai-voice/stream-stopped", {"session_id": session_id})
                except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError):
                    pass
            if poll_task:
                poll_task.cancel()
            if inbound_task:
                inbound_task.cancel()
            break


async def serve_forever(host, port, app_url, secret):
    if websockets is None:
        raise RuntimeError("Install websockets: pip install websockets")
    async def _handler(ws, path=None):
        await twilio_handler(app_url, secret, ws, path)

    async with websockets.serve(_handler, host, port, ping_interval=20):
        print(f"AI media bridge ws://{host}:{port} → app {app_url}", flush=True)
        await asyncio.Future()


def run_blocking(host, port, app_url, secret):
    asyncio.run(serve_forever(host, port, app_url, secret))


def run_in_thread(host, port, app_url, secret):
    thread = threading.Thread(
        target=run_blocking,
        args=(host, port, app_url, secret),
        name="ai-media-bridge",
        daemon=True,
    )
    thread.start()
    return thread


def maybe_start_embedded():
    """Start bridge in-process when AI_BRIDGE_EMBEDDED=true and secret is set."""
    from shared.config import APP_HOST, APP_PORT, ENV_PATH, read_env

    values = read_env(ENV_PATH)
    if str(values.get("AI_BRIDGE_EMBEDDED") or "").lower() != "true":
        return None
    secret = str(values.get("AI_BRIDGE_SECRET") or "").strip()
    if not secret:
        print("AI_BRIDGE_EMBEDDED is on but AI_BRIDGE_SECRET is empty.", flush=True)
        return None
    app_url = str(values.get("AI_BRIDGE_APP_URL") or f"http://{APP_HOST}:{APP_PORT}").rstrip("/")
    host = str(values.get("AI_BRIDGE_HOST") or "0.0.0.0")
    try:
        port = int(values.get("AI_BRIDGE_PORT") or "8766")
    except (TypeError, ValueError):
        port = 8766
    return run_in_thread(host, port, app_url, secret)
