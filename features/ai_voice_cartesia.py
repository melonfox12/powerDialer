"""Cartesia TTS → mulaw chunks for Twilio media streams."""

import base64
import json
import urllib.error
import urllib.request

from shared.infra import debug_event


def tts_mulaw_chunks(settings, text, *, chunk_size=160):
    """Return list of base64 mulaw payloads (~20ms at 8kHz when chunk_size=160)."""
    text = str(text or "").strip()
    if not text:
        return []
    key = str((settings or {}).get("CARTESIA_API_KEY") or "").strip()
    voice_id = str((settings or {}).get("CARTESIA_VOICE_ID") or "").strip()
    if not key:
        return []
    voice = {"mode": "id", "id": voice_id} if voice_id else {"mode": "id", "id": "a0e99841-438c-4a64-b679-ae501e7d6091"}
    payload = {
        "model_id": "sonic-2",
        "transcript": text,
        "voice": voice,
        "output_format": {
            "container": "raw",
            "encoding": "pcm_mulaw",
            "sample_rate": 8000,
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.cartesia.ai/tts/bytes",
        data=body,
        method="POST",
        headers={
            "X-API-Key": key,
            "Cartesia-Version": "2024-06-10",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        debug_event("error", "cartesia tts", f"{exc.code} {detail[:180]}")
        return []
    except urllib.error.URLError as exc:
        debug_event("error", "cartesia tts", str(exc.reason))
        return []
    chunks = []
    for offset in range(0, len(raw), chunk_size):
        chunks.append(base64.b64encode(raw[offset : offset + chunk_size]).decode("ascii"))
    return chunks
