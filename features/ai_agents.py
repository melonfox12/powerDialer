"""AI agent seats: reserved dialer pools and session mode."""

import json
import re
import uuid

from features import ai_agent_playbook
from features._dialer import calls, queue, slots
from features._dialer import projection
from shared.dial_policy import (
    agent_dial_queue,
    agent_reservation_blocks_other_apps,
    global_dialer_pool,
    is_agent_reserved,
    pick_agent_pool_ids,
)
from shared.vocabulary import (
    AGENT_POOL_SIZE,
    AI_AGENT_POOLS_JSON_KEY,
    agent_use_status_text,
)

DEFAULT_AGENT_SEATS = (
    {"id": "ava", "name": "Ava", "title": "Appointment setter", "primary": True},
    {"id": "miles", "name": "Miles", "title": "Appointment setter", "primary": False},
    {"id": "riley", "name": "Riley", "title": "Qualification", "primary": False},
    {"id": "jordan", "name": "Jordan", "title": "Appointment setter", "primary": False},
    {"id": "casey", "name": "Casey", "title": "Follow-up", "primary": False},
    {"id": "morgan", "name": "Morgan", "title": "Appointment setter", "primary": False},
    {"id": "quinn", "name": "Quinn", "title": "Reception bridge", "primary": False},
    {"id": "skyler", "name": "Skyler", "title": "Appointment setter", "primary": False},
)


def _default_agents():
    return [dict(item) for item in DEFAULT_AGENT_SEATS]


def _load_agents_data(state):
    raw = str((state.read_settings() or {}).get(AI_AGENT_POOLS_JSON_KEY) or "{}")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}
    pools = parsed.get("pools")
    if not isinstance(pools, dict):
        pools = {}
    agents = parsed.get("agents")
    if not isinstance(agents, list) or not agents:
        agents = _default_agents()
    else:
        agents = [
            record
            for item in agents
            if isinstance(item, dict)
            for record in [_normalize_agent_record(item)]
            if record
        ]
        if not agents:
            agents = _default_agents()
    parsed["pools"] = pools
    parsed["agents"] = agents
    return parsed


def _save_agents_data(state, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    values = {**state.read_settings(), AI_AGENT_POOLS_JSON_KEY: payload}
    state.settings = values
    if hasattr(state, "account_values"):
        state.account_values[AI_AGENT_POOLS_JSON_KEY] = payload
    saver = getattr(state, "settings_saver", None)
    if saver:
        saver(state)


def _normalize_agent_record(item):
    agent_id = str(item.get("id") or "").strip()
    name = str(item.get("name") or agent_id or "Agent").strip() or "Agent"
    title = str(item.get("title") or "AI dialer").strip() or "AI dialer"
    primary = bool(item.get("primary"))
    if not agent_id:
        return None
    return {"id": agent_id, "name": name, "title": title, "primary": primary}


def _agent_records(state):
    return list(_load_agents_data(state).get("agents") or [])


def _find_agent_record(state, agent_id):
    agent_id = str(agent_id or "").strip()
    for record in _agent_records(state):
        if record.get("id") == agent_id:
            return record
    return None


def _slugify_name(name, existing_ids):
    base = re.sub(r"[^a-z0-9]+", "-", str(name or "").strip().lower()).strip("-")[:32] or "agent"
    if base not in existing_ids:
        return base
    for index in range(2, 100):
        candidate = f"{base}-{index}"
        if candidate not in existing_ids:
            return candidate
    return f"agent-{uuid.uuid4().hex[:8]}"


def _primary_agent_id(records):
    for record in records:
        if record.get("primary"):
            return record["id"]
    return records[0]["id"] if records else "ava"


def _agent_name(agent_id, state=None):
    agent_id = str(agent_id or "").strip()
    if state is not None:
        record = _find_agent_record(state, agent_id)
        if record:
            return record["name"]
    for seat in DEFAULT_AGENT_SEATS:
        if seat["id"] == agent_id:
            return seat["name"]
    return agent_id or "Agent"


def all_reserved_lead_ids(state):
    blob = _load_agents_data(state)
    reserved = set()
    for ids in blob.get("pools", {}).values():
        for lead_id in ids or []:
            if lead_id:
                reserved.add(str(lead_id))
    return reserved


def agent_pool_lead_ids(state, agent_id):
    blob = _load_agents_data(state)
    ids = blob.get("pools", {}).get(str(agent_id), []) or []
    return [str(item) for item in ids if item]


def set_agent_pool_lead_ids(state, agent_id, lead_ids):
    blob = _load_agents_data(state)
    pools = blob.setdefault("pools", {})
    pools[str(agent_id)] = [str(item) for item in lead_ids if item]
    _save_agents_data(state, blob)


def create_agent(state, name, title=None):
    display = str(name or "").strip()
    if not display:
        raise ValueError("Agent name is required.")
    if len(display) > 80:
        raise ValueError("Agent name must be 80 characters or fewer.")
    role = str(title or "AI dialer").strip() or "AI dialer"
    if len(role) > 120:
        raise ValueError("Role must be 120 characters or fewer.")
    blob = _load_agents_data(state)
    agents = blob.setdefault("agents", [])
    existing_ids = {str(item.get("id") or "") for item in agents}
    agent_id = _slugify_name(display, existing_ids)
    record = {"id": agent_id, "name": display, "title": role, "primary": False}
    agents.append(record)
    blob.setdefault("pools", {}).setdefault(agent_id, [])
    _save_agents_data(state, blob)
    ai_agent_playbook.get_playbook(state, agent_id, display)
    state.record_activity(f"Created AI agent {display}", "web")
    return {"agent": record, "ai_agents": agents_public_view(state)}


def duplicate_agent(state, source_agent_id, name=None):
    source_id = str(source_agent_id or "").strip()
    source = _find_agent_record(state, source_id)
    if not source:
        raise ValueError("Source agent not found.")
    blob = _load_agents_data(state)
    agents = blob.setdefault("agents", [])
    existing_ids = {str(item.get("id") or "") for item in agents}
    display = str(name or "").strip() or f"{source['name']} copy"
    agent_id = _slugify_name(display, existing_ids)
    record = {
        "id": agent_id,
        "name": display,
        "title": source.get("title") or "AI dialer",
        "primary": False,
    }
    agents.append(record)
    blob.setdefault("pools", {}).setdefault(agent_id, [])
    _save_agents_data(state, blob)
    source_playbook = ai_agent_playbook.get_playbook(
        state, source_id, source["name"], require_ready=False,
    )
    ai_agent_playbook.save_playbook(
        state,
        agent_id,
        {"prompt": source_playbook.get("prompt") or ""},
        display,
    )
    state.record_activity(f"Duplicated {source['name']} as {display}", "web")
    return {"agent": record, "ai_agents": agents_public_view(state)}


def delete_agent(state, agent_id):
    agent_id = str(agent_id or "").strip()
    record = _find_agent_record(state, agent_id)
    if not record:
        raise ValueError("Agent not found.")
    if getattr(state, "running", False) and getattr(state, "ai_agent_id", None) == agent_id:
        raise ValueError("Stop this agent before deleting the seat.")
    blob = _load_agents_data(state)
    agents = blob.get("agents") or []
    if len(agents) < 2:
        raise ValueError("Keep at least one agent seat.")
    release_agent_pool(state, agent_id)
    ai_agent_playbook.remove_playbook(state, agent_id)
    agents = [item for item in agents if item.get("id") != agent_id]
    if record.get("primary") and agents:
        for item in agents:
            item["primary"] = False
        agents[0]["primary"] = True
    blob["agents"] = agents
    blob.get("pools", {}).pop(agent_id, None)
    _save_agents_data(state, blob)
    state.record_activity(f"Deleted agent seat {record['name']}", "web")
    return {"deleted": agent_id, "ai_agents": agents_public_view(state)}


def boot_agent_pool(state, agent_id):
    """Claim up to AGENT_POOL_SIZE prospects from the global dialer pool for one seat."""
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
    if not _find_agent_record(state, agent_id):
        raise ValueError("Agent seat not found.")
    existing = agent_pool_lead_ids(state, agent_id)
    if existing:
        return {"agent_id": agent_id, "lead_ids": existing, "created": False}
    leads = state.crm.snapshot()
    busy = calls._busy_lead_ids(state)
    reserved = all_reserved_lead_ids(state)
    chosen = pick_agent_pool_ids(
        leads,
        busy_ids=busy,
        reserved_ids=reserved,
        selected_timezone=state.selected_timezone,
        selected_business_type=getattr(state, "selected_business_type", None) or None,
        limit=AGENT_POOL_SIZE,
    )
    if not chosen:
        raise ValueError("No prospects are available to assign from the global dialer pool.")
    name = _agent_name(agent_id, state)
    for lead_id in chosen:
        state.crm.reserve_for_agent(lead_id, agent_id, name)
    set_agent_pool_lead_ids(state, agent_id, chosen)
    state.record_activity(f"{name} reserved {len(chosen)} prospects", "web")
    if (
        getattr(state, "ai_agent_mode", False)
        and getattr(state, "ai_agent_id", None) == agent_id
        and state.running
    ):
        try_resume_agent_dial(state)
    return {"agent_id": agent_id, "lead_ids": chosen, "created": True}


def release_agent_pool(state, agent_id, *, restore_status="new"):
    """Remove every prospect from a seat pool and clear agent-use locks."""
    agent_id = str(agent_id or "").strip()
    ids = agent_pool_lead_ids(state, agent_id)
    if not ids:
        set_agent_pool_lead_ids(state, agent_id, [])
        return {"released": 0}
    count = 0
    for lead_id in ids:
        lead = next((item for item in state.crm.snapshot() if item.get("id") == lead_id), None)
        if lead is None:
            continue
        if is_agent_reserved(lead):
            state.crm.agent_finalize_status(lead_id, restore_status, agent_id=agent_id)
            count += 1
    set_agent_pool_lead_ids(state, agent_id, [])
    state.record_activity(f"Released {count} prospects from {_agent_name(agent_id, state)}", "web")
    return {"released": count}


def dialable_pool_for_agent(state, leads=None):
    leads = leads if leads is not None else state.crm.snapshot()
    agent_id = getattr(state, "ai_agent_id", None)
    if not agent_id:
        return calls._pool_leads(state, leads)
    ids = agent_pool_lead_ids(state, agent_id)
    busy = calls._busy_lead_ids(state)
    return agent_dial_queue(ids, leads, busy)


def global_pool_snapshot(state):
    leads = state.crm.snapshot()
    busy = calls._busy_lead_ids(state)
    pool = global_dialer_pool(
        leads,
        busy_ids=busy,
        selected_timezone=state.selected_timezone,
        selected_business_type=getattr(state, "selected_business_type", None) or None,
    )
    return {
        "dialer_pool": pool,
        "dialer_pool_count": len(pool),
    }


def agents_public_view(state):
    blob = _load_agents_data(state)
    pools = blob.get("pools", {})
    records = blob.get("agents") or _default_agents()
    running_id = getattr(state, "ai_agent_id", None)
    primary_id = _primary_agent_id(records)
    agents = []
    leads = state.crm.snapshot()
    busy = calls._busy_lead_ids(state)
    for record in records:
        agent_id = record["id"]
        lead_ids = pools.get(agent_id, []) or []
        dialable = len(agent_dial_queue(lead_ids, leads, busy)) if lead_ids else 0
        agents.append({
            "id": agent_id,
            "name": record["name"],
            "title": record.get("title") or "AI dialer",
            "pool_size": len(lead_ids),
            "pool_dialable": dialable,
            "running": running_id == agent_id and state.running,
            "primary": agent_id == primary_id,
        })
    snapshot = global_pool_snapshot(state)
    stats = agent_pool_stats(state, running_id) if running_id else {"agent_pool_total": 0, "agent_pool_dialable": 0}
    return {
        "agents": agents,
        "global_dialer_pool_count": snapshot["dialer_pool_count"],
        "running_agent_id": running_id if state.running else None,
        "agent_pools": pools,
        "agent_pool_total": stats["agent_pool_total"],
        "agent_pool_dialable": stats["agent_pool_dialable"],
    }


def agent_pool_stats(state, agent_id=None):
    agent_id = str(agent_id or getattr(state, "ai_agent_id", None) or "").strip()
    ids = agent_pool_lead_ids(state, agent_id) if agent_id else []
    dialable = dialable_pool_for_agent(state) if agent_id else []
    return {
        "agent_pool_total": len(ids),
        "agent_pool_dialable": len(dialable),
    }


def try_resume_agent_dial(state):
    """Refill lines when the agent pool gains dialable prospects and no live call is up."""
    if not getattr(state, "ai_agent_mode", False):
        return
    with state.lock:
        if state.active or state.pending_outcome or not state.running or state.paused:
            return
        from features._dialer import voice_session
        if not voice_session.slots_may_dial(state):
            return
    dialable = dialable_pool_for_agent(state)
    if len(dialable) < 1:
        with state.lock:
            state.ai_dial_starved = True
        return
    with state.lock:
        state.ai_dial_starved = False
    slots.fill_slots(state)


def start_agent(state, agent_id):
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
    if not _find_agent_record(state, agent_id):
        raise ValueError("Agent seat not found.")
    with state.lock:
        if state.running:
            if getattr(state, "ai_agent_id", None) == agent_id:
                raise ValueError("This agent is already running.")
            raise ValueError("Another dialer session is already running.")
    boot_agent_pool(state, agent_id)
    stats = agent_pool_stats(state, agent_id)
    if stats["agent_pool_total"] < 1:
        raise ValueError("Agent pool is empty. Nothing was reserved from the global dialer pool.")
    if stats["agent_pool_dialable"] < 1:
        raise ValueError("Agent pool has no dialable prospects right now (need New or static Dialed).")
    with state.lock:
        state.ai_agent_id = agent_id
        state.ai_agent_mode = True
        state.ai_dial_starved = False
    view = queue.start(state)
    view["ai_agents"] = agents_public_view(state)
    return view


def stop_agent(state, agent_id):
    agent_id = str(agent_id or "").strip()
    with state.lock:
        running_id = getattr(state, "ai_agent_id", None)
    if state.running and running_id and running_id != agent_id:
        raise ValueError("A different agent session is running.")
    view = queue.stop(state)
    with state.lock:
        state.ai_agent_id = None
        state.ai_agent_mode = False
    view["ai_agents"] = agents_public_view(state)
    return view


def finalize_agent_call(state, lead_id, *, connected, voicemail=False):
    """Auto CRM updates for AI sessions — dialed or contact_engaged only."""
    if not getattr(state, "ai_agent_mode", False):
        return
    agent_id = getattr(state, "ai_agent_id", None)
    lead = next((item for item in state.crm.snapshot() if item.get("id") == lead_id), None)
    if lead is None or agent_reservation_blocks_other_apps(lead, agent_id):
        return
    if connected and not voicemail:
        state.crm.agent_finalize_status(lead_id, "contact_engaged", agent_id=agent_id)
    else:
        state.crm.agent_finalize_status(lead_id, "dialed", agent_id=agent_id)


def assert_lead_mutable_by_user(state, lead_id):
    lead = next((item for item in state.crm.snapshot() if item.get("id") == lead_id), None)
    if lead is None:
        return
    if agent_reservation_blocks_other_apps(lead):
        name = agent_use_status_text(lead)
        raise ValueError(f"{name} — this prospect is reserved for an AI agent.")


def agent_lead_ids_for_queue(state):
    return agent_pool_lead_ids(state, getattr(state, "ai_agent_id", None) or "")
