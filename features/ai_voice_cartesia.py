"""Cartesia TTS → mulaw chunks for Twilio media streams."""

import base64
import json
import urllib.error
import urllib.request

from shared.infra import debug_event
from shared.vocabulary import CARTESIA_SANDBOX_SAMPLE_RATE, CARTESIA_TTS_MODEL


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


def _voice_spec(settings):
    voice_id = str((settings or {}).get("CARTESIA_VOICE_ID") or "").strip()
    if voice_id:
        return {"mode": "id", "id": voice_id}
    return {"mode": "id", "id": "a0e99841-438c-4a64-b679-ae501e7d6091"}


def _fetch_tts_bytes(settings, text, *, encoding, sample_rate):
    text = str(text or "").strip()
    if not text:
        return b"", "empty transcript"
    key = str((settings or {}).get("CARTESIA_API_KEY") or "").strip()
    if not key:
        return b"", "Cartesia API key is missing — add CARTESIA_API_KEY in Settings."
    model_id = str((settings or {}).get("CARTESIA_TTS_MODEL") or CARTESIA_TTS_MODEL).strip() or CARTESIA_TTS_MODEL
    payload = {
        "model_id": model_id,
        "transcript": text,
        "voice": _voice_spec(settings),
        "output_format": {
            "container": "raw",
            "encoding": encoding,
            "sample_rate": sample_rate,
        },
    }
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
