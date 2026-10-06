"""Fill the single prospect slot."""

import random

def fill_slots(state):
    leads = state.crm.snapshot()
    launches = []
    with state.lock:
        if not state.running or state.paused or not state.agent_ready or state.active or state.pending_outcome:
            return
        active_leads = {call["lead_id"] for call in state.in_flight.values()}
        slots = max(0, 1 - len(state.in_flight))
        manual = state._claim_manual_lead(leads, active_leads) if slots else None
        if manual:
            selected = [manual]
        else:
            pool = [
                lead for lead in state._pool_leads(leads)
                if lead["id"] not in active_leads
            ]
            selected = random.sample(pool, min(slots, len(pool)))
        for lead in selected:
            call = state._new_call("prospect", lead)
            call["caller_id"] = state._next_caller()
            launches.append((call, lead["phone"]))
    for call, destination in launches:
        state._launch_call(call, destination)
    state._schedule_calling_window_check()
