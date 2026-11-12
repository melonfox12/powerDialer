"""Desk sandbox: user plays prospect; agent uses seat prompt + LLM (no Twilio)."""

from datetime import datetime, timezone

from features import ai_agent_playbook, ai_agents, ai_voice_llm

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


def _agent_name(state, agent_id):
    return ai_agents._agent_name(agent_id)


def _system_prompt(state, agent_id, prospect):
    playbook = ai_agent_playbook.get_playbook(state, agent_id, _agent_name(state, agent_id))
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


def _opening_reply(state, system_prompt):
    try:
        return ai_voice_llm.chat_reply(
            state.read_settings(),
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": "The prospect just answered. Give a short opening line."}],
        )
    except ai_voice_llm.LlmError:
        return ai_voice_llm._fallback_reply([])


def start(state, agent_id, prospect=None):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
    if state.running:
        raise ValueError("Stop the live dialer before using sandbox mode.")
    system = _system_prompt(state, agent_id, prospect)
    opening = _opening_reply(state, system)
    messages = [{"role": "assistant", "content": opening}]
    transcript = [_transcript_line("Agent", opening)]
    with state.lock:
        state.ai_sandbox_sessions[agent_id] = {
            "agent_id": agent_id,
            "system_prompt": system,
            "messages": messages,
            "transcript": transcript,
            "prospect": {**_DEFAULT_PROSPECT, **(prospect or {})},
        }
    state.record_activity(f"Sandbox started for {_agent_name(state, agent_id)}", "dialer")
    return _public(state, agent_id)


def turn(state, agent_id, text):
    agent_id = str(agent_id or "").strip()
    text = str(text or "").strip()
    if not text:
        raise ValueError("Type something as the prospect.")
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if not session:
            raise ValueError("Turn on sandbox mode first.")
        session["messages"].append({"role": "user", "content": text})
        session["transcript"].append(_transcript_line("Prospect", text))
        history = list(session["messages"])
        system = session["system_prompt"]
    try:
        reply = ai_voice_llm.chat_reply(state.read_settings(), system_prompt=system, messages=history)
    except ai_voice_llm.LlmError as exc:
        raise ValueError(str(exc)) from exc
    lowered = reply.lower()
    if "[end_call]" in lowered:
        reply = reply.replace("[END_CALL]", "").replace("[end_call]", "").strip()
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
        if session:
            session["messages"].append({"role": "assistant", "content": reply})
            session["transcript"].append(_transcript_line("Agent", reply))
            session["ended"] = "[end_call]" in lowered
    return _public(state, agent_id)


def reset(state, agent_id):
    agent_id = str(agent_id or "").strip()
    with state.lock:
        state.ai_sandbox_sessions.pop(agent_id, None)
    return {"agent_id": agent_id, "active": False, "transcript": [], "messages": []}


def _public(state, agent_id):
    with state.lock:
        session = state.ai_sandbox_sessions.get(agent_id)
    if not session:
        return {"agent_id": agent_id, "active": False, "transcript": [], "messages": []}
    return {
        "agent_id": agent_id,
        "active": True,
        "ended": bool(session.get("ended")),
        "transcript": list(session.get("transcript") or []),
        "messages": list(session.get("messages") or []),
        "prospect": dict(session.get("prospect") or {}),
    }


def active_for_agent(state, agent_id):
    with state.lock:
        return bool(state.ai_sandbox_sessions.get(str(agent_id or "").strip()))
