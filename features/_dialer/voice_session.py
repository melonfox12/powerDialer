"""Voice session profile: human browser desk vs AI line (Cartesia)."""

from shared.vocabulary import VOICE_PROFILE_AI_CARTESIA, VOICE_PROFILE_HUMAN_BROWSER


def voice_profile(state):
    return getattr(state, "voice_profile", None) or VOICE_PROFILE_HUMAN_BROWSER


def is_ai_voice(state):
    return voice_profile(state) == VOICE_PROFILE_AI_CARTESIA


def uses_browser_agent_leg(state):
    """Whether the session expects a Twilio browser / agent conference leg."""
    return not is_ai_voice(state)


def slots_may_dial(state):
    """Whether parallel prospect slots may be filled."""
    if not state.running or state.paused:
        return False
    if is_ai_voice(state):
        return bool(getattr(state, "ai_voice_armed", False))
    return bool(state.agent_ready)


def begin_human_voice_session(state):
    with state.lock:
        state.voice_profile = VOICE_PROFILE_HUMAN_BROWSER
        state.ai_voice_armed = False
        state.agent_ready = False


def begin_ai_voice_session(state):
    with state.lock:
        state.voice_profile = VOICE_PROFILE_AI_CARTESIA
        state.ai_voice_armed = True
        state.agent_ready = True
        state.last_event = "AI voice armed"


def reset_voice_session(state):
    with state.lock:
        state.voice_profile = VOICE_PROFILE_HUMAN_BROWSER
        state.ai_voice_armed = False


def attach_call_voice_defaults(state, call):
    call["voice_profile"] = voice_profile(state)
    call.setdefault("bridge_session_id", "")
    call.setdefault("transcript_source", "twilio")


def requires_browser_voice(state):
    return state.running and uses_browser_agent_leg(state)
