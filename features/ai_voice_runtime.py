"""In-call AI voice sessions: prompt, LLM turns, outbound audio queue."""

import secrets
import threading
import time
import urllib.parse

from features import ai_agent_playbook, ai_voice_cartesia, ai_voice_disposition, ai_voice_llm
from features._dialer import live_transcript, twilio, voice_session
from shared.dial_policy import agent_reservation_blocks_other_apps
from shared.vocabulary import TRANSCRIPT_SOURCE_CARTESIA, TRANSCRIPT_SOURCE_TWILIO

_MAX_CALL_SECONDS = 900
_SILENCE_HANGUP_SECONDS = 45


def get_session(state, session_id):
    with state.lock:
        return state.ai_voice_sessions.get(session_id)


def voice_configured(settings):
    settings = settings or {}
    return bool(
        str(settings.get("AI_BRIDGE_WSS_URL") or "").strip()
        and str(settings.get("AI_BRIDGE_SECRET") or "").strip()
    )


def bridge_secret_ok(state, provided):
    expected = str(state.read_settings().get("AI_BRIDGE_SECRET") or "").strip()
    if not expected:
        return False
    return secrets.compare_digest(expected, str(provided or ""))


def _lead_context(lead):
    lead = lead or {}
    return {
        "id": lead.get("id") or "",
        "name": lead.get("name") or "",
        "business": lead.get("business") or "",
        "phone": lead.get("phone") or "",
        "status": lead.get("status") or "",
    }


def _touch(session):
    session["last_activity_at"] = time.monotonic()


def _schedule_watchers(state, session_id):
    def _max_call():
        session = get_session(state, session_id)
        if not session or session.get("ended"):
            return
        uuid = session.get("call_uuid")
        if uuid:
            twilio._hangup_call(state, uuid)

    def _silence_tick():
        while True:
            time.sleep(5)
            session = get_session(state, session_id)
            if not session or session.get("ended"):
                return
            last = float(session.get("last_activity_at") or 0)
            if last and time.monotonic() - last > _SILENCE_HANGUP_SECONDS:
                uuid = session.get("call_uuid")
                if uuid:
                    twilio._hangup_call(state, uuid)
                return

    threading.Timer(_MAX_CALL_SECONDS, _max_call).start()
    threading.Thread(target=_silence_tick, daemon=True).start()


def start_call_session(state, call):
    if not voice_session.is_ai_voice(state):
        return None
    existing = call.get("bridge_session_id")
    if existing and get_session(state, existing):
        return existing
    settings = state.read_settings()
    agent_id = getattr(state, "ai_agent_id", None) or "ava"
    name = call.get("lead", {}).get("name") or agent_id
    playbook = ai_agent_playbook.get_playbook(state, agent_id, name)
    session_id = "avs-" + secrets.token_hex(10)
    lead_ctx = _lead_context(call.get("lead"))
    system = playbook["compiled"]["system_prompt"]
    lead_block = "\n".join(f"{key}: {value}" for key, value in lead_ctx.items() if value)
    if lead_block:
        system = f"{system}\n\nProspect on this call:\n{lead_block}"
    with state.lock:
        call["bridge_session_id"] = session_id
        call["transcript_source"] = TRANSCRIPT_SOURCE_CARTESIA
        state.ai_voice_sessions[session_id] = {
            "session_id": session_id,
            "call_token": call["token"],
            "call_uuid": call.get("call_uuid") or "",
            "lead_id": call.get("lead_id"),
            "agent_id": agent_id,
            "system_prompt": system,
            "messages": [],
            "outbound_chunks": [],
            "outbound_cursor": 0,
            "stream_active": False,
            "ended": False,
            "last_prospect_key": "",
            "inbound_mulaw": bytearray(),
            "silence_frames": 0,
            "heard_voice": False,
            "last_activity_at": time.monotonic(),
        }
    state.record_activity("AI voice session armed", "call")
    return session_id


def ai_stream_twiml(state, call):
    settings = state.read_settings()
    if not voice_configured(settings):
        msg = twilio.escape_xml("AI voice is not configured. Set bridge WSS URL and secret in Settings.")
        return f"<Response><Say>{msg}</Say><Hangup/></Response>"
    wss = str(settings.get("AI_BRIDGE_WSS_URL") or "").strip()
    session_id = call.get("bridge_session_id") or ""
    joiner = "&" if "?" in wss else "?"
    stream_url = f"{wss}{joiner}session={urllib.parse.quote(session_id, safe='')}"
    token = twilio.escape_xml(call["token"])
    sid = twilio.escape_xml(session_id)
    return (
        "<Response>"
        f'<Start><Stream url="{twilio.escape_xml(stream_url)}" track="inbound_track">'
        f'<Parameter name="session" value="{sid}"/>'
        f'<Parameter name="callToken" value="{token}"/>'
        "</Stream></Start>"
        '<Pause length="3600"/>'
        "</Response>"
    )


def _queue_speech(state, session_id, text, *, speaker="Agent"):
    session = get_session(state, session_id)
    if not session or not text:
        return
    with state.lock:
        storage = state.calls.get(session["call_token"])
        _touch(session)
    if storage:
        live_transcript.append_final(
            state, storage, speaker=speaker, text=text, source=TRANSCRIPT_SOURCE_CARTESIA,
        )
    chunks = ai_voice_cartesia.tts_mulaw_chunks(state.read_settings(), text)
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if not session:
            return
        session["outbound_chunks"].extend(chunks)
        if not chunks:
            state.record_activity("AI spoke (text only — add CARTESIA_API_KEY for audio)", "call")


def kickoff_conversation(state, session_id):
    def _run():
        session = get_session(state, session_id)
        if not session:
            return
        try:
            text = ai_voice_llm.chat_reply(
                state.read_settings(),
                system_prompt=session["system_prompt"],
                messages=[{"role": "user", "content": "The prospect just answered. Give a short opening line."}],
            )
        except ai_voice_llm.LlmError as exc:
            state.record_activity(f"AI opening skipped: {exc}", "error")
            text = ai_voice_llm._fallback_reply([
                {"role": "user", "content": "The prospect just answered. Give a short opening line."},
            ])
        with state.lock:
            session = state.ai_voice_sessions.get(session_id)
            if session:
                session["messages"].append({"role": "assistant", "content": text})
        _queue_speech(state, session_id, text)

    threading.Thread(target=_run, daemon=True).start()


def on_prospect_text(state, call, text, *, source="twilio"):
    if not voice_session.is_ai_voice(state):
        return
    session_id = call.get("bridge_session_id")
    text = str(text or "").strip()
    if not session_id or not text:
        return
    if source == "twilio":
        session = get_session(state, session_id)
        if session and session.get("stream_active"):
            return
    key = text.lower()
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if not session or session.get("ended"):
            return
        if session.get("last_prospect_key") == key:
            return
        session["last_prospect_key"] = key
        _touch(session)
    transcript_source = TRANSCRIPT_SOURCE_TWILIO if source == "twilio" else TRANSCRIPT_SOURCE_CARTESIA
    live_transcript.append_final(
        state, call, speaker="Prospect", text=text, source=transcript_source,
    )

    def _run():
        with state.lock:
            session = state.ai_voice_sessions.get(session_id)
            if not session or session.get("ended"):
                return
            session["messages"].append({"role": "user", "content": text})
            history = list(session["messages"])
            system = session["system_prompt"]
        try:
            reply = ai_voice_llm.chat_reply(state.read_settings(), system_prompt=system, messages=history)
        except ai_voice_llm.LlmError as exc:
            state.record_activity(f"AI reply failed: {exc}", "error")
            return
        lowered = reply.lower()
        if "[end_call]" in lowered:
            reply = reply.replace("[END_CALL]", "").replace("[end_call]", "").strip()
        with state.lock:
            session = state.ai_voice_sessions.get(session_id)
            if session:
                session["messages"].append({"role": "assistant", "content": reply})
        _queue_speech(state, session_id, reply)
        if "[end_call]" in lowered and call.get("call_uuid"):
            threading.Timer(1.2, twilio._hangup_call, args=(state, call["call_uuid"])).start()

    threading.Thread(target=_run, daemon=True).start()


def mark_stream_started(state, session_id):
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if session:
            session["stream_active"] = True
            _touch(session)
    _schedule_watchers(state, session_id)
    kickoff_conversation(state, session_id)


def stream_sync(state, session_id):
    with state.lock:
        session = state.ai_voice_sessions.get(session_id)
        if not session:
            return {"chunks": [], "ended": True}
        start = session["outbound_cursor"]
        chunks = session["outbound_chunks"][start:]
        session["outbound_cursor"] = len(session["outbound_chunks"])
        return {"chunks": chunks, "ended": bool(session.get("ended"))}


def finish_session(state, session_id):
    lead_id = None
    agent_id = None
    messages = []
    with state.lock:
        session = state.ai_voice_sessions.pop(session_id, None)
        if not session:
            return
        session["ended"] = True
        lead_id = session.get("lead_id")
        agent_id = session.get("agent_id")
        messages = session.get("messages") or []
        call = state.calls.get(session.get("call_token") or "")
        if call and lead_id and messages:
            call["ai_disposition_done"] = True
    if not lead_id or not messages:
        return
    status = ai_voice_disposition.suggest_status(state.read_settings(), messages)
    lead = next((item for item in state.crm.snapshot() if item.get("id") == lead_id), None)
    if lead is None or agent_reservation_blocks_other_apps(lead, agent_id):
        return
    state.crm.agent_finalize_status(lead_id, status, agent_id=agent_id)


def end_session(state, session_id):
    finish_session(state, session_id)


def purge_sessions(state):
    with state.lock:
        ids = list(state.ai_voice_sessions)
    for session_id in ids:
        finish_session(state, session_id)


def bootstrap(state, session_id):
    session = get_session(state, session_id)
    if not session:
        return None
    return {
        "session_id": session_id,
        "call_token": session.get("call_token"),
        "call_uuid": session.get("call_uuid"),
        "lead_id": session.get("lead_id"),
    }


def public_status(state):
    settings = state.read_settings()
    active = 0
    with state.lock:
        active = sum(1 for item in state.ai_voice_sessions.values() if not item.get("ended"))
    return {
        "ai_voice_configured": voice_configured(settings),
        "ai_voice_stream_active": active > 0,
        "ai_voice_sessions": active,
    }
