"""Cartesia TTS → mulaw chunks for Twilio media streams."""

import base64
import http.client
import json
import re
import urllib.error
import urllib.request

from shared.infra import debug_event
from shared.vocabulary import CARTESIA_SANDBOX_SAMPLE_RATE, CARTESIA_TTS_MODEL

_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
_DEFAULT_VOICE_ID = "a0e99841-438c-4a64-b679-ae501e7d6091"


def _parse_error_detail(raw):
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:200]
    if isinstance(payload, dict):
        for key in ("message", "error", "detail"):
            value = payload.get(key)
            if value:
                return str(value)[:200]
    return raw[:200]


def _normalize_voice_id(raw):
    voice_id = str(raw or "").strip().strip('"').strip("'")
    if not voice_id:
        return ""
    if _UUID_RE.match(voice_id):
        return voice_id.lower()
    return ""


def _voice_id(settings):
    """Cartesia API (2026-08-14) expects voice as a UUID string or {\"id\": \"...\"}, not legacy mode/id."""
    raw = str((settings or {}).get("CARTESIA_VOICE_ID") or "").strip()
    custom = _normalize_voice_id(raw)
    if raw and not custom:
        debug_event("warn", "cartesia voice", f"invalid CARTESIA_VOICE_ID {raw[:40]!r}; using default voice")
    return custom or _DEFAULT_VOICE_ID


def _fetch_tts_bytes(settings, text, *, encoding, sample_rate):
    text = str(text or "").strip()
    if not text:
        return b"", "empty transcript"
    key = str((settings or {}).get("CARTESIA_API_KEY") or "").strip()
    if not key:
        return b"", "Cartesia API key is missing — add CARTESIA_API_KEY in Settings."
    model_id = str((settings or {}).get("CARTESIA_TTS_MODEL") or CARTESIA_TTS_MODEL).strip() or CARTESIA_TTS_MODEL
    voice_id = _voice_id(settings)
    payload = {
        "model_id": model_id,
        "transcript": text,
        "voice": voice_id,
        "output_format": {
            "container": "raw",
            "encoding": encoding,
            "sample_rate": sample_rate,
        },
    }
    if _normalize_voice_id((settings or {}).get("CARTESIA_VOICE_ID")):
        debug_event("cartesia", "tts", f"model={model_id} voice=…{voice_id[-8:]} rate={sample_rate}")
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes",
        data=body,
        method="POST",
        headers={
            "X-API-Key": key,
            "Cartesia-Version": "2026-08-14",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        summary = _parse_error_detail(detail)
        message = f"Cartesia TTS HTTP {exc.code}: {summary}"
        debug_event("error", "cartesia tts", message)
        return b"", message
    except urllib.error.URLError as exc:
        message = f"Cartesia TTS unreachable: {exc.reason}"
        debug_event("error", "cartesia tts", message)
        return b"", message
    if not raw:
        return b"", "Cartesia TTS returned empty audio."
    return raw, ""


def _chunk_bytes(raw, chunk_size):
    chunks = []
    for offset in range(0, len(raw), chunk_size):
        chunks.append(base64.b64encode(raw[offset : offset + chunk_size]).decode("ascii"))
    return chunks


def tts_mulaw_chunks(settings, text, *, chunk_size=160):
    """Return (base64 mulaw chunk strings, error message). error is \"\" on success."""
    raw, err = _fetch_tts_bytes(settings, text, encoding="pcm_mulaw", sample_rate=8000)
    if err:
        return [], err
    return _chunk_bytes(raw, chunk_size), ""


def tts_sandbox_chunks(settings, text, *, chunk_size=8192):
    """Higher-fidelity PCM for browser headphones (not Twilio 8 kHz mulaw)."""
    raw, err = _fetch_tts_bytes(
        settings,
        text,
        encoding="pcm_s16le",
        sample_rate=CARTESIA_SANDBOX_SAMPLE_RATE,
    )
    if err:
        return [], err
    return _chunk_bytes(raw, chunk_size), ""


SANDBOX_AUDIO_META = {
    "audio_encoding": "pcm_s16le",
    "audio_sample_rate": CARTESIA_SANDBOX_SAMPLE_RATE,
}

SANDBOX_STREAM_CHUNK_BYTES = 2880  # ~60 ms PCM at 24 kHz mono s16le


def _emit_pcm_chunks(pcm_buf, chunk_size, emit):
    while len(pcm_buf) >= chunk_size:
        piece = bytes(pcm_buf[:chunk_size])
        del pcm_buf[:chunk_size]
        emit(base64.b64encode(piece).decode("ascii"))


def _cartesia_sse_request(settings, text, *, encoding, sample_rate, on_pcm):
    key = str((settings or {}).get("CARTESIA_API_KEY") or "").strip()
    if not key:
        return "Cartesia API key is missing — add CARTESIA_API_KEY in Settings."
    model_id = str((settings or {}).get("CARTESIA_TTS_MODEL") or CARTESIA_TTS_MODEL).strip() or CARTESIA_TTS_MODEL
    voice_id = _voice_id(settings)
    payload = {
        "model_id": model_id,
        "transcript": text,
        "voice": voice_id,
        "output_format": {
            "container": "raw",
            "encoding": encoding,
            "sample_rate": sample_rate,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    conn = http.client.HTTPSConnection("api.cartesia.ai", timeout=90)
    try:
        conn.request(
            "POST",
            "/tts/sse",
            body=body,
            headers={
                "X-API-Key": key,
                "Cartesia-Version": "2026-08-14",
                "Content-Type": "application/json",
                "Accept": "text/event-stream",
            },
        )
        response = conn.getresponse()
        if response.status >= 400:
            detail = response.read(4096).decode("utf-8", errors="replace")
            return f"Cartesia TTS HTTP {response.status}: {_parse_error_detail(detail)}"
        data_line = b""
        while True:
            raw = response.readline()
            if not raw:
                break
            line = raw.strip()
            if not line:
                if not data_line:
                    continue
                try:
                    event = json.loads(data_line.decode("utf-8"))
                except json.JSONDecodeError:
                    data_line = b""
                    continue
                data_line = b""
                kind = event.get("type")
                if kind == "chunk":
                    chunk = base64.b64decode(event.get("data") or "")
                    if chunk:
                        on_pcm(chunk)
                elif kind == "error":
                    return str(event.get("message") or event.get("title") or "Cartesia TTS error.")
                elif kind == "done":
                    break
                continue
            if line.startswith(b"data:"):
                data_line = line[5:].strip()
    except OSError as exc:
        return f"Cartesia TTS unreachable: {exc}"
    finally:
        conn.close()
    return ""


def tts_sandbox_stream(settings, text, emit_chunk, *, chunk_size=SANDBOX_STREAM_CHUNK_BYTES):
    """Stream sandbox PCM via Cartesia SSE; emit_chunk(b64) as bytes arrive."""
    text = str(text or "").strip()
    if not text:
        return "empty transcript"
    pending = bytearray()

    def on_pcm(pcm):
        pending.extend(pcm)
        _emit_pcm_chunks(pending, chunk_size, emit_chunk)

    err = _cartesia_sse_request(
        settings,
        text,
        encoding="pcm_s16le",
        sample_rate=CARTESIA_SANDBOX_SAMPLE_RATE,
        on_pcm=on_pcm,
    )
    if err:
        chunks, fallback_err = tts_sandbox_chunks(settings, text, chunk_size=chunk_size)
        if fallback_err:
            return err if "HTTP" in err else fallback_err
        for chunk in chunks:
            emit_chunk(chunk)
        return ""
    if pending:
        emit_chunk(base64.b64encode(bytes(pending)).decode("ascii"))
    return ""


def tts_mulaw_stream(settings, text, emit_chunk, *, chunk_size=160):
    pending = bytearray()

    def on_pcm(pcm):
        pending.extend(pcm)
        _emit_pcm_chunks(pending, chunk_size, emit_chunk)

    err = _cartesia_sse_request(
        settings,
        text,
        encoding="pcm_mulaw",
        sample_rate=8000,
        on_pcm=on_pcm,
    )
    if err:
        chunks, fallback_err = tts_mulaw_chunks(settings, text, chunk_size=chunk_size)
        if fallback_err:
            return err if "HTTP" in err else fallback_err
        for chunk in chunks:
            emit_chunk(chunk)
        return ""
    if pending:
        emit_chunk(base64.b64encode(bytes(pending)).decode("ascii"))
    return ""
