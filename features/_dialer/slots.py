"""Fill the single prospect slot, and the calling-window timer that refills it."""

import threading

from features._dialer import calls, rules


def fill_slots(state):
    try:
        _place_prospect_call(state)
    except Exception as exc:
        state.record_activity(f"Could not start the next call: {exc}", "error")


def _place_prospect_call(state):
    leads = state.crm.snapshot()
    launches = []
    none_ready = False
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
            selected = pool[:open_slots]
        if open_slots and not selected:
            none_ready = True
        for lead in selected:
            call = calls._new_call(state, "prospect", lead)
            call["caller_id"] = calls._next_caller(state)
            launches.append((call, lead["phone"]))
    if none_ready:
        state.record_activity("No prospect was ready to dial", "call")
    for call, destination in launches:
        name = (call.get("lead") or {}).get("name") or "prospect"
        state.record_activity(f"Dialing {name}", "call")
        calls._launch_call(state, call, destination)
    rules._flush_metrics(state)
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
