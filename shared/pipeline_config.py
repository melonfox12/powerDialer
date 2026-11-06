"""Configurable CRM pipeline steps: Dialed + Contacted (engaged) (call_1) are fixed; the rest are user-defined."""

import json
import re
from copy import deepcopy

from shared.vocabulary import (
    PIPELINE_DIALED_STEP,
    PIPELINE_SEND_INFO_STEP,
    PIPELINE_STEPS as DEFAULT_PIPELINE_STEPS,
)

_PIPELINE_STEP_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_MAX_PIPELINE_KEY_LEN = 63

# Only these two columns are not editable or removable.
LOCKED_PIPELINE_KEYS = frozenset({PIPELINE_DIALED_STEP, PIPELINE_SEND_INFO_STEP})


def normalize_pipeline_step_key(raw):
    """Turn user input into a valid step key: lowercase, letters/digits, underscores between words.

    Examples: "Follow Up" -> "follow_up", "Email #1" -> "email_1", "123" -> "step_123".
    Returns "" if nothing usable remains."""
    s = str(raw or "").strip().lower()
    parts = []
    buf = []
    for ch in s:
        if "a" <= ch <= "z" or ch.isdigit():
            buf.append(ch)
        else:
            if buf:
                parts.append("".join(buf))
                buf = []
    if buf:
        parts.append("".join(buf))
    key = "_".join(parts)
    key = key.strip("_")
    if not key:
        return ""
    if key[0].isdigit():
        key = "step_" + key
    if len(key) > _MAX_PIPELINE_KEY_LEN:
        key = key[:_MAX_PIPELINE_KEY_LEN].rstrip("_")
    if not key or not key[0].isalpha():
        return ""
    return key

_DEFAULT_BY_KEY = {item["key"]: dict(item) for item in DEFAULT_PIPELINE_STEPS}
_DEFAULT_TAIL_KEYS = [item["key"] for item in DEFAULT_PIPELINE_STEPS if item["key"] not in LOCKED_PIPELINE_KEYS]


def _as_step_dict(raw):
    if not isinstance(raw, dict):
        return None
    key = normalize_pipeline_step_key(raw.get("key"))
    label = str(raw.get("label") or "").strip()
    try:
        wait_hours = int(float(raw.get("wait_hours")))
    except (TypeError, ValueError):
        return None
    if not key or not label:
        return None
    if key in LOCKED_PIPELINE_KEYS:
        return None
    if not _PIPELINE_STEP_KEY_RE.match(key):
        return None
    if wait_hours < 0 or wait_hours > 24 * 365:
        return None
    if len(label) > 120:
        return None
    return {"key": key, "label": label, "wait_hours": wait_hours}


def parse_custom_pipeline_steps_json(text):
    """Parse stored JSON list of custom tail steps. Returns (steps, error_message)."""
    stripped = str(text or "").strip()
    if not stripped:
        return [], None
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        return [], f"Pipeline steps JSON is not valid: {exc}"
    if not isinstance(data, list):
        return [], "Pipeline steps must be a JSON array."
    seen = set()
    out = []
    for item in data:
        step = _as_step_dict(item)
        if step is None:
            return [], "Each step needs a valid key, label, and wait_hours (non-negative hours)."
        if step["key"] in seen:
            return [], f"Duplicate step key: {step['key']}"
        seen.add(step["key"])
        out.append(step)
    return out, None


def merge_pipeline_steps(custom_tail):
    """Full ordered step list: locked head + custom tail (defaults when custom empty)."""
    head = [
        dict(_DEFAULT_BY_KEY[PIPELINE_DIALED_STEP]),
        dict(_DEFAULT_BY_KEY[PIPELINE_SEND_INFO_STEP]),
    ]
    if not custom_tail:
        tail = [dict(_DEFAULT_BY_KEY[k]) for k in _DEFAULT_TAIL_KEYS]
    else:
        tail = [dict(s) for s in custom_tail]
    return head + tail


def resolve_pipeline_steps(account_values):
    """Steps for API/catalog from env/account settings."""
    raw = ""
    if account_values:
        raw = str(account_values.get("PIPELINE_CUSTOM_STEPS_JSON") or "").strip()
    custom, _err = parse_custom_pipeline_steps_json(raw)
    return merge_pipeline_steps(custom)


def validate_pipeline_tail_payload(steps):
    """Validate user POST body steps (tail only). Returns (normalized_list, error_message)."""
    if not isinstance(steps, list):
        return None, "Expected a JSON array of steps."
    if len(steps) > 40:
        return None, "At most 40 custom pipeline steps."
    seen = set()
    out = []
    for item in steps:
        if not isinstance(item, dict):
            return None, "Each step must be an object."
        step = _as_step_dict(item)
        if step is None:
            return None, "Each step needs key (a-z, numbers, underscore), label, and wait_hours."
        if step["key"] in seen:
            return None, f"Duplicate key: {step['key']}"
        seen.add(step["key"])
        out.append(step)
    return out, None


def migrate_leads_pipeline_keys(leads, old_keys, new_keys, send_info_step, dialed_step):
    """Remap pipeline_step / pipeline_history when step keys disappear. Returns lead ids touched."""
    old_keys = set(old_keys)
    new_keys = set(new_keys)
    removed = old_keys - new_keys
    if not removed:
        return []
    fallback_send = send_info_step
    touched = []

    def map_step(key, status):
        k = str(key or "").strip()
        if k in new_keys:
            return k, False
        if k in removed:
            if status == "dialed":
                return dialed_step, True
            return fallback_send, True
        return k, False

    for lead in leads:
        changed = False
        status = str(lead.get("status") or "")
        ps = str(lead.get("pipeline_step") or "").strip()
        new_ps, c = map_step(ps, status)
        if c:
            lead["pipeline_step"] = new_ps
            changed = True
        hist = lead.get("pipeline_history")
        if isinstance(hist, list):
            for entry in hist:
                if not isinstance(entry, dict):
                    continue
                sk = str(entry.get("step") or "").strip()
                nk, c = map_step(sk, status)
                if c:
                    entry["step"] = nk
                    changed = True
        if changed:
            touched.append(lead["id"])
    return touched
