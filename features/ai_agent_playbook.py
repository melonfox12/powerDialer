"""Per-seat AI call playbooks — single freeform prompt per agent."""

import hashlib
import json
import re
from datetime import datetime, timezone

from shared.vocabulary import AI_AGENT_PLAYBOOKS_JSON_KEY

DEFAULT_PROMPT_TEMPLATE = """You are {agent_name}, a professional outbound caller.

Goal: Pre-qualify receptionists and decision makers. Stay calm, concise, and respectful of gatekeepers.

How to speak:
- Short sentences. Mirror their pace. Say your company name once clearly.
- Pause after questions; do not talk over the prospect.

How to act:
- Follow your steps below but handle natural detours.
- If wrong person, politely ask for the decision maker by title.
- If not a fit, thank them and end cleanly.

Must say:
- Your name and company on connect.

Never say:
- Guaranteed ROI or pressure tactics.

Steps (improvise wording; keep intent):
1. Intro — greet, company, ask if now is a bad time.
2. Role — confirm decision maker or route through receptionist.
3. Qualify — 2–3 short fit/timing questions.
4. Next step — book or send info if qualified.
5. Close — confirm next step and end warmly.
"""

_RUNTIME_FOOTER = """
[Live call behavior]
- Speak in short, natural phone sentences; do not read markdown or bullet symbols aloud.
- Follow the playbook above; adapt wording but keep each step's intent.
- When the conversation is finished, include [END_CALL] in your final reply.
"""


def default_prompt_text(agent_name="Agent"):
    return DEFAULT_PROMPT_TEMPLATE.format(agent_name=agent_name).strip()


def legacy_dict_to_prompt(data):
    """Flatten older structured playbooks into one prompt block."""
    lines = []
    title = str(data.get("title") or "").strip()
    if title:
        lines.append(f"# {title}")
    for key, heading in (
        ("persona", "Persona"),
        ("objective", "Objective"),
        ("dialogue", "Dialogue"),
        ("actions", "Actions"),
    ):
        value = str(data.get(key) or "").strip()
        if value:
            lines.extend(["", heading, value])
    target = str(data.get("target_role") or "").strip()
    if target and target != "either":
        lines.extend(["", f"Primary target: {target.replace('_', ' ')}"])
    guard = data.get("guardrails") if isinstance(data.get("guardrails"), dict) else {}
    must = [str(item).strip() for item in (guard.get("must_say") or []) if str(item).strip()]
    never = [str(item).strip() for item in (guard.get("never_say") or []) if str(item).strip()]
    if must:
        lines.extend(["", "Must say:", *[f"- {item}" for item in must]])
    if never:
        lines.extend(["", "Never say:", *[f"- {item}" for item in never]])
    steps = data.get("steps") if isinstance(data.get("steps"), list) else []
    if steps:
        lines.extend(["", "Steps:"])
        for index, step in enumerate(steps, start=1):
            if not isinstance(step, dict):
                continue
            label = step.get("label") or step.get("id") or f"Step {index}"
            lines.append(f"{index}. {label}")
            if step.get("dialogue"):
                lines.append(f"   Say: {step['dialogue']}")
            if step.get("actions"):
                lines.append(f"   Do: {step['actions']}")
    return "\n".join(lines).strip()


def _load_blob(state):
    raw = str((state.read_settings() or {}).get(AI_AGENT_PLAYBOOKS_JSON_KEY) or "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    playbooks = parsed.get("playbooks")
    if not isinstance(playbooks, dict):
        playbooks = {}
    return {"playbooks": playbooks}


def _save_blob(state, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    values = {**state.read_settings(), AI_AGENT_PLAYBOOKS_JSON_KEY: payload}
    state.settings = values
    if hasattr(state, "account_values"):
        state.account_values[AI_AGENT_PLAYBOOKS_JSON_KEY] = payload
    saver = getattr(state, "settings_saver", None)
    if saver:
        saver(state)


def _extract_prompt(raw, agent_name="Agent"):
    if isinstance(raw, str):
        text = raw.strip()
        return text or default_prompt_text(agent_name)
    if not isinstance(raw, dict):
        return default_prompt_text(agent_name)
    prompt = str(raw.get("prompt") or "").strip()
    if prompt:
        return prompt
    legacy = legacy_dict_to_prompt(raw)
    return legacy or default_prompt_text(agent_name)


def _prompt_digest(prompt):
    return hashlib.sha256(str(prompt or "").encode("utf-8")).hexdigest()[:16]


def _resolve_placeholders(prompt, agent_name):
    text = str(prompt or "")
    return text.replace("{agent_name}", agent_name)


def _step_ids_from_prompt(prompt):
    ids = []
    for line in str(prompt or "").splitlines():
        stripped = line.strip()
        match = re.match(r"^(\d+)[.)]\s*(.+)", stripped)
        if match:
            ids.append(f"step-{match.group(1)}")
    return ids


def compile_playbook(playbook, agent_name="Agent"):
    prompt = _resolve_placeholders(str((playbook or {}).get("prompt") or "").strip(), agent_name)
    if not prompt:
        prompt = default_prompt_text(agent_name).strip()
    system_prompt = f"[Agent seat: {agent_name}]\n\n{prompt}{_RUNTIME_FOOTER}".strip()
    digest = _prompt_digest(prompt)
    return {
        "system_prompt": system_prompt,
        "step_ids": _step_ids_from_prompt(prompt),
        "compiled_at": datetime.now(timezone.utc).isoformat(),
        "prompt_digest": digest,
    }


def normalize_playbook(raw, agent_name="Agent"):
    prompt = _extract_prompt(raw, agent_name)
    playbook = {"prompt": prompt}
    playbook["compiled"] = compile_playbook(playbook, agent_name)
    playbook["execution_ready"] = True
    return playbook


def _stored_record(playbook):
    return {
        "prompt": playbook["prompt"],
        "compiled": dict(playbook["compiled"]),
    }


def _playbook_view(raw, agent_name):
    prompt = _extract_prompt(raw, agent_name)
    stored_compiled = raw.get("compiled") if isinstance(raw, dict) else None
    digest = _prompt_digest(prompt)
    ready = (
        isinstance(stored_compiled, dict)
        and str(stored_compiled.get("system_prompt") or "").strip()
        and stored_compiled.get("prompt_digest") == digest
    )
    if ready:
        compiled = {
            "system_prompt": str(stored_compiled["system_prompt"]),
            "step_ids": list(stored_compiled.get("step_ids") or []),
            "compiled_at": stored_compiled.get("compiled_at") or "",
            "prompt_digest": stored_compiled.get("prompt_digest") or digest,
        }
    else:
        compiled = compile_playbook({"prompt": prompt}, agent_name)
    return {
        "prompt": prompt,
        "compiled": compiled,
        "execution_ready": ready,
    }


def _persist_playbook(state, agent_id, playbook):
    blob = _load_blob(state)
    blob.setdefault("playbooks", {})[agent_id] = _stored_record(playbook)
    _save_blob(state, blob)


def _legacy_missing_compiled(raw):
    if not isinstance(raw, dict):
        return False
    if not str(raw.get("prompt") or "").strip():
        return False
    compiled = raw.get("compiled")
    return not isinstance(compiled, dict) or not str(compiled.get("system_prompt") or "").strip()


def default_playbook(agent_name="Agent"):
    return normalize_playbook({"prompt": default_prompt_text(agent_name)}, agent_name)


def get_playbook(state, agent_id, agent_name="Agent", *, require_ready=False):
    agent_id = str(agent_id or "").strip()
    blob = _load_blob(state)
    raw = blob.get("playbooks", {}).get(agent_id)
    if not raw:
        playbook = default_playbook(agent_name)
        _persist_playbook(state, agent_id, playbook)
        return playbook
    if _legacy_missing_compiled(raw):
        playbook = normalize_playbook(raw, agent_name)
        _persist_playbook(state, agent_id, playbook)
        playbook["execution_ready"] = True
        if require_ready:
            return playbook
        return playbook
    playbook = _playbook_view(raw, agent_name)
    if require_ready and not playbook["execution_ready"]:
        raise ValueError("Save the agent prompt to compile call instructions before dialing.")
    return playbook


def remove_playbook(state, agent_id):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        return
    blob = _load_blob(state)
    playbooks = blob.get("playbooks")
    if isinstance(playbooks, dict) and agent_id in playbooks:
        del playbooks[agent_id]
        _save_blob(state, blob)


def save_playbook(state, agent_id, payload, agent_name="Agent"):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
    if isinstance(payload, dict) and "playbook" in payload:
        payload = payload.get("playbook")
    if isinstance(payload, dict) and payload.get("prompt") is None and len(payload) > 1:
        payload = {"prompt": legacy_dict_to_prompt(payload)}
    elif isinstance(payload, dict) and "prompt" not in payload and isinstance(payload.get("playbook"), dict):
        payload = payload["playbook"]
    playbook = normalize_playbook(payload if isinstance(payload, dict) else {"prompt": payload}, agent_name)
    _persist_playbook(state, agent_id, playbook)
    return playbook
