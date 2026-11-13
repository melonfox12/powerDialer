"""Desk sandbox: mic as prospect; agent uses same LLM + Cartesia path as live AI voice."""

import base64
import threading
import time
from datetime import datetime, timezone

from features import ai_agent_playbook, ai_agents, ai_voice_cartesia, ai_voice_llm, ai_voice_stt

_SANDBOX_NOTE = (
    "\n\n[Simulation] You are on a training call. The other party is a teammate role-playing "
    "as the prospect. Respond as you would on a live outbound call."
)

_DEFAULT_PROSPECT = {
    "name": "Jordan",
    "business": "Sample Services LLC",
    "phone": "+1 555 0100",
    "status": "New",
}

_MULAW_FRAME = 160
_SILENCE_RMS = 100
_SILENCE_FRAMES = 20
_MIN_UTTERANCE = 3200


def _agent_name(state, agent_id):
    return ai_agents._agent_name(agent_id, state)


def _system_prompt(state, agent_id, prospect):
    playbook = ai_agent_playbook.get_playbook(
        state, agent_id, _agent_name(state, agent_id), require_ready=True,
    )
    system = playbook["compiled"]["system_prompt"] + _SANDBOX_NOTE
    prospect = {**_DEFAULT_PROSPECT, **(prospect or {})}
    block = "\n".join(f"{key}: {value}" for key, value in prospect.items() if value)
    if block:
        system = f"{system}\n\nProspect in this simulation:\n{block}"
    return system


def _transcript_line(speaker, text):
    return {
        "speaker": speaker,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "id": f"sandbox-{speaker}-{datetime.now(timezone.utc).timestamp()}",
    }


def _bump_transcript(session, line):
    session["transcript"].append(line)
    session["transcript_seq"] = int(session.get("transcript_seq") or 0) + 1


def _mark_outbound_delivered(session):
    session["outbound_cursor"] = len(session.get("outbound_chunks") or [])


def _append_sandbox_chunk(state, agent_id, chunk_b64):
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            return
        session.setdefault("outbound_chunks", []).append(chunk_b64)
        session["outbound_audio"] = dict(ai_voice_cartesia.SANDBOX_AUDIO_META)


def _run_sandbox_tts(state, agent_id, text):
    settings = state.read_settings()

    def emit(chunk_b64):
        _append_sandbox_chunk(state, agent_id, chunk_b64)

    try:
        err = ai_voice_cartesia.tts_sandbox_stream(settings, text, emit)
        if err:
            state.record_activity(f"Sandbox: {err}", "error")
        else:
            with state.lock:
                session = state.ai_sandbox_sessions.get(agent_id)
                empty = bool(session) and not session.get("outbound_chunks")
            if empty:
                state.record_activity(
                    "Sandbox: Cartesia returned no audio (check CARTESIA_API_KEY / voice id in Settings).",
                    "error",
                )
    finally:
        with state.lock:
            session = state.ai_sandbox_sessions.get(agent_id)
            if session:
                session["tts_busy"] = False


def _start_sandbox_tts(state, agent_id, text):
    text = str(text or "").strip()
    if not text:
        return
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            return
        session["tts_busy"] = True
    threading.Thread(target=_run_sandbox_tts, args=(state, agent_id, text), daemon=True).start()


def _opening_reply(state, system_prompt):
    try:
        return ai_voice_llm.chat_reply(
            state.read_settings(),
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "The prospect just answered. Give a short opening line."}],
        )
    except ai_voice_llm.LlmError:
        return ai_voice_llm._fallback_reply([])


def _session_template(agent_id, system, prospect, opening):
    return {
        "agent_id": agent_id,
        "system_prompt": system,
        "messages": [{"role": "assistant", "content": opening}],
        "transcript": [_transcript_line("Agent", opening)],
        "transcript_seq": 1,
        "prospect": {**_DEFAULT_PROSPECT, **(prospect or {})},
        "outbound_chunks": [],
        "outbound_cursor": 0,
        "inbound_mulaw": bytearray(),
        "silence_frames": 0,
        "heard_voice": False,
        "last_prospect_key": "",
        "reply_busy": False,
        "ended": False,
    }


def _apply_agent_reply(state, agent_id, reply):
    lowered = reply.lower()
    if "[end_call]" in lowered:
        reply = reply.replace("[END_CALL]", "").replace("[end_call]", "").strip()
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            return False, "", []
        session["messages"].append({"role": "assistant", "content": reply})
        _bump_transcript(session, _transcript_line("Agent", reply))
        session["ended"] = "[end_call]" in lowered
    _start_sandbox_tts(state, agent_id, reply)
    return True, reply, []


def _prospect_turn(state, agent_id, text, *, from_stt=False):
    text = str(text or "").strip()
    if not text:
        if from_stt:
            return _public(state, agent_id)
        raise ValueError("Say something as the prospect.")
    key = text.lower()
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            if from_stt:
                return {"agent_id": agent_id, "active": False, "transcript": [], "messages": []}
            raise ValueError("Turn on sandbox mode first.")
        if session.get("ended"):
            return _public(state, agent_id)
        if session.get("last_prospect_key") == key:
            return _public(state, agent_id)
        session["last_prospect_key"] = key
        session["messages"].append({"role": "user", "content": text})
        _bump_transcript(session, _transcript_line("Prospect", text))
        history = list(session["messages"])
        system = session["system_prompt"]
    try:
        reply = ai_voice_llm.chat_reply(state.read_settings(), system_prompt=system, messages=history)
    except ai_voice_llm.LlmError as exc:
        if from_stt:
            state.record_activity(f"Sandbox AI reply failed: {exc}", "error")
            return _public(state, agent_id)
        raise ValueError(str(exc)) from exc
    _ok, _reply, audio_chunks = _apply_agent_reply(state, agent_id, reply)
    return _public(state, agent_id, audio_chunks=audio_chunks)


def _wait_playback_ready(state, agent_id, timeout=90.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with state.lock:
            session = state.ai_sandbox_sessions.get(agent_id)
            if not session:
                return False
            if session.get("playback_ready"):
                return True
        time.sleep(0.05)
    return False


def _boot_session(state, agent_id, system, prospect):
    opening = _opening_reply(state, system)
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            return
        session["messages"] = [{"role": "assistant", "content": opening}]
        session["transcript"] = [_transcript_line("Agent", opening)]
        session["transcript_seq"] = 1
    if not _wait_playback_ready(state, agent_id):
        state.record_activity("Sandbox: browser speaker path not ready in time", "error")
    _start_sandbox_tts(state, agent_id, opening)
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if session:
            session["booting"] = False


def mark_playback_ready(state, agent_id):
    agent_id = str(agent_id or "").strip()
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if session:
            session["playback_ready"] = True
    return _public(state, agent_id)


def start(state, agent_id, prospect=None):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
    if state.running:
        raise ValueError("Stop the live dialer before using sandbox mode.")
    system = _system_prompt(state, agent_id, prospect)
    prospect_merged = {**_DEFAULT_PROSPECT, **(prospect or {})}
    with state.lock:
        state.ai_sandbox_sessions[agent_id] = {
            "agent_id": agent_id,
            "system_prompt": system,
            "messages": [],
            "transcript": [],
            "transcript_seq": 0,
            "prospect": prospect_merged,
            "outbound_chunks": [],
            "outbound_cursor": 0,
            "inbound_mulaw": bytearray(),
            "silence_frames": 0,
            "heard_voice": False,
            "last_prospect_key": "",
            "reply_busy": False,
            "tts_busy": False,
            "booting": True,
            "playback_ready": False,
            "ended": False,
        }
    threading.Thread(target=_boot_session, args=(state, agent_id, system, prospect), daemon=True).start()
    state.record_activity(f"Sandbox voice started for {_agent_name(state, agent_id)}", "dialer")
    return _public(state, agent_id)


def turn(state, agent_id, text):
    return _prospect_turn(state, agent_id, text, from_stt=False)


def _collect_utterances(session, chunk):
    """Step VAD in 20 ms mulaw frames (same cadence as the live media bridge)."""
    utterances = []
    if not chunk:
        return utterances
    buf = session.setdefault("inbound_mulaw", bytearray())
    for offset in range(0, len(chunk), _MULAW_FRAME):
        frame = chunk[offset : offset + _MULAW_FRAME]
        if len(frame) < _MULAW_FRAME:
            frame = frame + bytes([0xFF] * (_MULAW_FRAME - len(frame)))
        buf.extend(frame)
        rms = ai_voice_stt.mulaw_rms(frame)
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
            continue
        utterances.append(bytes(buf))
        buf.clear()
        session["silence_frames"] = 0
        session["heard_voice"] = False
    return utterances


def ingest_mulaw(state, agent_id, payload_b64):
    agent_id = str(agent_id or "").strip()
    try:
        chunk = base64.b64decode(payload_b64)
    except (ValueError, TypeError):
        return
    if not chunk:
        return
    utterances = []
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session or session.get("ended") or session.get("reply_busy"):
            return
        utterances = _collect_utterances(session, chunk)
    for utterance in utterances:
        threading.Thread(target=_transcribe_and_turn, args=(state, agent_id, utterance), daemon=True).start()


def _transcribe_and_turn(state, agent_id, utterance):
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session or session.get("ended"):
            return
        session["reply_busy"] = True
    try:
        text = ai_voice_stt.transcribe_mulaw(state.read_settings(), utterance, min_rms=60)
        if text:
            _prospect_turn(state, agent_id, text, from_stt=True)
        else:
            state.record_activity("Sandbox: could not transcribe mic audio (speak louder or check OPENAI_API_KEY)", "dialer")
    finally:
        with state.lock:
            session = state.ai_sandbox_sessions.get(agent_id)
            if session:
                session["reply_busy"] = False


def _audio_meta(session):
    meta = dict(session.get("outbound_audio") or ai_voice_cartesia.SANDBOX_AUDIO_META)
    return {
        "audio_encoding": str(meta.get("audio_encoding") or "pcm_s16le"),
        "audio_sample_rate": int(meta.get("audio_sample_rate") or ai_voice_cartesia.SANDBOX_AUDIO_META["audio_sample_rate"]),
    }


def stream_sync(state, agent_id):
    agent_id = str(agent_id or "").strip()
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            return {
                "agent_id": agent_id,
                "chunks": [],
                "ended": True,
                "transcript": [],
                "transcript_seq": 0,
                "reply_busy": False,
            }
        start = int(session.get("outbound_cursor") or 0)
        pending = list(session.get("outbound_chunks") or [])[start:]
        if session.get("playback_ready"):
            chunks = pending
            session["outbound_cursor"] = len(session.get("outbound_chunks") or [])
        else:
            chunks = []
        return {
            "agent_id": agent_id,
            "chunks": chunks,
            "ended": bool(session.get("ended")),
            "transcript": list(session.get("transcript") or []),
            "transcript_seq": int(session.get("transcript_seq") or 0),
            "reply_busy": bool(session.get("reply_busy") or session.get("booting") or session.get("tts_busy")),
            "booting": bool(session.get("booting")),
            "tts_busy": bool(session.get("tts_busy")),
            **_audio_meta(session),
        }


def reset(state, agent_id):
    agent_id = str(agent_id or "").strip()
    with state.lock:
        state.ai_sandbox_sessions.pop(agent_id, None)
    return {"agent_id": agent_id, "active": False, "transcript": [], "messages": []}


def _public(state, agent_id, audio_chunks=None):
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
    if not session:
        return {"agent_id": agent_id, "active": False, "transcript": [], "messages": []}
    payload = {
        "agent_id": agent_id,
        "active": True,
        "ended": bool(session.get("ended")),
        "transcript": list(session.get("transcript") or []),
        "transcript_seq": int(session.get("transcript_seq") or 0),
        "messages": list(session.get("messages") or []),
        "prospect": dict(session.get("prospect") or {}),
        "reply_busy": bool(session.get("reply_busy") or session.get("booting") or session.get("tts_busy")),
        "booting": bool(session.get("booting")),
        "tts_busy": bool(session.get("tts_busy")),
    }
    if audio_chunks:
        payload["chunks"] = list(audio_chunks)
        with state.lock:
            session = state.ai_sandbox_sessions.get(agent_id)
            if session:
                _mark_outbound_delivered(session)
    payload.update(_audio_meta(session))
    return payload


def active_for_agent(state, agent_id):
    with state.lock:
        return bool(state.ai_sandbox_sessions.get(str(agent_id or "").strip()))
