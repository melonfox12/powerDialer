"""Per-seat AI call playbooks — single freeform prompt per agent."""

import json

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


def normalize_playbook(raw, agent_name="Agent"):
    prompt = _extract_prompt(raw, agent_name)
    playbook = {"prompt": prompt}
    playbook["compiled"] = compile_playbook(playbook)
    return playbook


def compile_playbook(playbook):
    prompt = str((playbook or {}).get("prompt") or "").strip()
    return {"system_prompt": prompt, "step_ids": []}


def default_playbook(agent_name="Agent"):
    return normalize_playbook({"prompt": default_prompt_text(agent_name)}, agent_name)


def get_playbook(state, agent_id, agent_name="Agent"):
    agent_id = str(agent_id or "").strip()
    blob = _load_blob(state)
    raw = blob.get("playbooks", {}).get(agent_id)
    if not raw:
        return default_playbook(agent_name)
    return normalize_playbook(raw, agent_name)


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
    blob = _load_blob(state)
    blob.setdefault("playbooks", {})[agent_id] = {"prompt": playbook["prompt"]}
    _save_blob(state, blob)
    return playbook
