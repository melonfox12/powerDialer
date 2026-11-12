"""Buffer bridge mulaw; detect end of utterance; STT."""

import base64
import threading

from features import ai_voice_stt
from features import ai_voice_runtime

_SILENCE_RMS = 180
_SILENCE_FRAMES = 25
_MIN_UTTERANCE = 4800


def ingest_mulaw(state, session_id, payload_b64):
    session = ai_voice_runtime.get_session(state, session_id)
    if not session or session.get("ended"):
        return
    try:
        chunk = base64.b64decode(payload_b64)
    except (ValueError, TypeError):
        return
    if not chunk:
        return
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if not session or session.get("ended"):
            return
        buf = session.setdefault("inbound_mulaw", bytearray())
        buf.extend(chunk)
        rms = ai_voice_stt.mulaw_rms(chunk)
        silent = rms < _SILENCE_RMS
        if silent:
            session["silence_frames"] = int(session.get("silence_frames") or 0) + 1
        else:
            session["silence_frames"] = 0
            session["heard_voice"] = True
        flush = (
            session.get("heard_voice")
            and int(session.get("silence_frames") or 0) >= _SILENCE_FRAMES
            and len(buf) >= _MIN_UTTERANCE
        )
        if not flush:
            return
        utterance = bytes(buf)
        buf.clear()
        session["silence_frames"] = 0
        session["heard_voice"] = False
    threading.Thread(target=_transcribe_and_reply, args=(state, session_id, utterance), daemon=True).start()


def _transcribe_and_reply(state, session_id, utterance):
    text = ai_voice_stt.transcribe_mulaw(state.read_settings(), utterance)
    if not text:
        return
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if not session:
            return
        call = state.calls.get(session.get("call_token"))
    if not call:
        return
    ai_voice_runtime.on_prospect_text(state, call, text, source="bridge_stt")
