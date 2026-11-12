"""Prospect audio → text (8 kHz mulaw buffer → Whisper)."""

import base64
import io
import json
import struct
import urllib.error
import urllib.request
import wave

_MULAW_BIAS = 0x84
_MULAW_CLIP = 32635


def _mulaw_decode(byte):
    byte = ~byte & 0xFF
    sign = byte & 0x80
    exponent = (byte >> 4) & 0x07
    mantissa = byte & 0x0F
    sample = ((mantissa << 3) + _MULAW_BIAS) << exponent
    sample -= _MULAW_BIAS
    if sign:
        sample = -sample
    return max(-32768, min(32767, sample))


def mulaw_rms(mulaw_chunk):
    if not mulaw_chunk:
        return 0
    total = 0
    for byte in mulaw_chunk:
        sample = _mulaw_decode(byte)
        total += sample * sample
    return (total / len(mulaw_chunk)) ** 0.5


def mulaw_to_wav(mulaw_bytes):
    pcm = bytearray()
    for byte in mulaw_bytes:
        sample = _mulaw_decode(byte)
        pcm.extend(struct.pack("<h", sample))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(8000)
        handle.writeframes(pcm)
    return buf.getvalue()


def transcribe_mulaw(settings, mulaw_bytes, *, min_rms=120):
    if len(mulaw_bytes) < 1600:
        return ""
    if mulaw_rms(mulaw_bytes) < min_rms:
        return ""
    key = str((settings or {}).get("OPENAI_API_KEY") or "").strip()
    if not key:
        return ""
    wav = mulaw_to_wav(mulaw_bytes)
    boundary = "----pdmulaw"
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="file"; filename="clip.wav"\r\n',
        b"Content-Type: audio/wav\r\n\r\n",
        wav,
        f"\r\n--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="model"\r\n\r\n',
        b"whisper-1\r\n",
        f"--{boundary}\r\n".encode(),
        b'Content-Disposition: form-data; name="language"\r\n\r\n',
        b"en\r\n",
        f"--{boundary}--\r\n".encode(),
    ])
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/transcriptions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, KeyError):
        return ""
    return str(data.get("text") or "").strip()
