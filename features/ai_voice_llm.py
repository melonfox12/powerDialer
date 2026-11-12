"""LLM replies for AI voice (OpenAI-compatible chat API)."""

import json
import urllib.error
import urllib.request

from shared.infra import debug_event


class LlmError(Exception):
    pass


def chat_reply(settings, *, system_prompt, messages):
    """Return assistant text for one turn."""
    key = str((settings or {}).get("OPENAI_API_KEY") or "").strip()
    if not key:
        return _fallback_reply(messages)
    model = str((settings or {}).get("AI_LLM_MODEL") or "gpt-4o-mini").strip()
    payload = {
        "model": model,
        "temperature": 0.6,
        "messages": [{"role": "system", "content": system_prompt}, *messages],
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/chat/completions",
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=45) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise LlmError(f"LLM HTTP {exc.code}: {detail[:200]}") from exc
    except urllib.error.URLError as exc:
        raise LlmError(f"LLM unreachable: {exc.reason}") from exc
    try:
        return str(data["choices"][0]["message"]["content"]).strip()
    except (KeyError, IndexError, TypeError) as exc:
        debug_event("error", "llm parse", str(exc))
        raise LlmError("LLM returned an unexpected response.") from exc


def _fallback_reply(messages):
    """Short reply when no API key — keeps calls from hanging silently in dev."""
    last_user = ""
    for item in reversed(messages):
        if item.get("role") == "user":
            last_user = str(item.get("content") or "")
            break
    if last_user:
        return (
            "Thanks for taking my call. I am still being configured for live AI speech, "
            "but I heard you. Could you tell me the best person to speak with about this?"
        )
    return (
        "Hi — thanks for picking up. I am calling for a quick introduction. "
        "Is now an okay time for a brief conversation?"
    )
