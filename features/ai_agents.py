"""AI agent seats: reserved dialer pools and session mode."""

import json

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

AGENT_CATALOG = {
    "ava": "Ava",
    "miles": "Miles",
    "riley": "Riley",
    "jordan": "Jordan",
    "casey": "Casey",
    "morgan": "Morgan",
    "quinn": "Quinn",
    "skyler": "Skyler",
}


def _agent_name(agent_id):
    return AGENT_CATALOG.get(str(agent_id or "").strip()) or str(agent_id or "").strip() or "Agent"


def _load_pools_blob(state):
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
    return {"pools": pools}


def _save_pools_blob(state, data):
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    values = {**state.read_settings(), AI_AGENT_POOLS_JSON_KEY: payload}
    state.settings = values
    if hasattr(state, "account_values"):
        state.account_values[AI_AGENT_POOLS_JSON_KEY] = payload
    saver = getattr(state, "settings_saver", None)
    if saver:
        saver(state)


def all_reserved_lead_ids(state):
    blob = _load_pools_blob(state)
    reserved = set()
    for ids in blob.get("pools", {}).values():
        for lead_id in ids or []:
            if lead_id:
                reserved.add(str(lead_id))
    return reserved


def agent_pool_lead_ids(state, agent_id):
    blob = _load_pools_blob(state)
    ids = blob.get("pools", {}).get(str(agent_id), []) or []
    return [str(item) for item in ids if item]


def set_agent_pool_lead_ids(state, agent_id, lead_ids):
    blob = _load_pools_blob(state)
    pools = blob.setdefault("pools", {})
    pools[str(agent_id)] = [str(item) for item in lead_ids if item]
    _save_pools_blob(state, blob)


def boot_agent_pool(state, agent_id):
    """Claim up to AGENT_POOL_SIZE prospects from the global dialer pool for one seat."""
    agent_id = str(agent_id or "").strip()
    if not agent_id:
        raise ValueError("Choose an agent seat.")
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
    name = _agent_name(agent_id)
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
    state.record_activity(f"Released {count} prospects from {_agent_name(agent_id)}", "web")
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
    blob = _load_pools_blob(state)
    pools = blob.get("pools", {})
    running_id = getattr(state, "ai_agent_id", None)
    agents = []
    leads = state.crm.snapshot()
    busy = calls._busy_lead_ids(state)
    for agent_id, display in AGENT_CATALOG.items():
        lead_ids = pools.get(agent_id, []) or []
        dialable = len(agent_dial_queue(lead_ids, leads, busy)) if lead_ids else 0
        agents.append({
            "id": agent_id,
            "name": display,
            "pool_size": len(lead_ids),
            "pool_dialable": dialable,
            "running": running_id == agent_id and state.running,
            "primary": agent_id == "ava",
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
