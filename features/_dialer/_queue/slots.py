"""Fill the single prospect slot, and the calling-window timer that refills it."""

import random
import threading

from features._dialer._queue import calls


def fill_slots(state):
    leads = state.crm.snapshot()
    launches = []
    with state.lock:
        if not state.running or state.paused or not state.agent_ready or state.active or state.pending_outcome:
            return
        active_leads = {call["lead_id"] for call in state.in_flight.values()}
        open_slots = max(0, 1 - len(state.in_flight))
        manual = calls._claim_manual_lead(state, leads, active_leads) if open_slots else None
        if manual:
            selected = [manual]
        else:
            pool = [
                lead for lead in calls._pool_leads(state, leads)
                if lead["id"] not in active_leads
            ]
            selected = random.sample(pool, min(open_slots, len(pool)))
        for lead in selected:
            call = calls._new_call(state, "prospect", lead)
            call["caller_id"] = calls._next_caller(state)
            launches.append((call, lead["phone"]))
    for call, destination in launches:
        calls._launch_call(state, call, destination)
    _schedule_calling_window_check(state)


def _schedule_calling_window_check(state):
    with state.lock:
        if state.calling_window_timer:
            state.calling_window_timer.cancel()
            state.calling_window_timer = None
        if not state.running or state.paused:
            return
        state.calling_window_timer = threading.Timer(60, _check_calling_window, args=(state,))
        state.calling_window_timer.daemon = True
        state.calling_window_timer.start()


def _check_calling_window(state):
    with state.lock:
        state.calling_window_timer = None
        should_fill = state.running and not state.paused and not state.active and not state.pending_outcome
    if should_fill:
        fill_slots(state)
    else:
        _schedule_calling_window_check(state)
