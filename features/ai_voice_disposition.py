"""Map conversation to a CRM status at end of AI call."""

from features import ai_voice_llm

_ALLOWED = frozenset({"contact_engaged", "dialed", "qualified", "closed"})


def suggest_status(settings, messages):
    if not messages:
        return "dialed"
    prompt = (
        "Given this call transcript as JSON messages, reply with ONE word only: "
        "contact_engaged, dialed, qualified, or closed. "
        "Use qualified when clear fit; closed when not interested; contact_engaged when conversation happened but no clear outcome."
    )
    try:
        raw = ai_voice_llm.chat_reply(
            settings,
            system_prompt=prompt,
            messages=[{"role": "user", "content": str(messages[-12:])}],
        )
    except ai_voice_llm.LlmError:
        return "contact_engaged"
    key = raw.strip().lower().split()[0] if raw.strip() else "contact_engaged"
    return key if key in _ALLOWED else "contact_engaged"
