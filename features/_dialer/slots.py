"""Fill the open prospect lines, and the calling-window timer that refills them."""

import threading

from features._dialer import calls, rules


def _prune_finished_lines(state):
    """Drop ended lines still listed in in_flight so open slots can refill."""
    with state.lock:
        rules.clear_stale_active(state)
        for token, call in list(state.in_flight.items()):
            if call.get("end_processed") or call.get("skip_closed"):
                state.in_flight.pop(token, None)
                if state.active is call:
                    state.active = None
            elif call.get("cancelled") and not call.get("picked_up"):
                state.in_flight.pop(token, None)
                if state.active is call:
                    state.active = None


def fill_slots(state):
    try:
        _place_prospect_call(state)
    except Exception as exc:
        state.record_activity(f"Could not start the next call: {exc}", "error")


def request_top_up(state):
    """Fill any open dial slots while other lines may still be ringing."""
    threading.Thread(target=fill_slots, args=(state,), daemon=True).start()


def _place_prospect_call(state):
    _prune_finished_lines(state)
    launches = []
    none_ready = False
    with state.lock:
        rules.clear_stale_active(state)
        if not state.running or state.paused or not state.agent_ready or state.active or state.pending_outcome:
            return
        prospect_lines = [
            call for call in state.in_flight.values() if call.get("kind") == "prospect"
        ]
        open_slots = max(0, len(state.callers) - len(prospect_lines))
        if open_slots <= 0:
            return
        leads = state.crm.snapshot()
        active_leads = {call["lead_id"] for call in state.in_flight.values() if call.get("lead_id")}
        selected = []
        taken = set()
        if open_slots:
            manual = calls._claim_manual_lead(state, leads, active_leads)
            if manual:
                selected.append(manual)
                active_leads.add(manual["id"])
                taken |= calls._contact_keys(manual)
                open_slots -= 1
        if open_slots:
            pool = [
                lead for lead in calls._pool_leads(state, leads)
                if lead["id"] not in active_leads and not (calls._contact_keys(lead) & taken)
            ]
            selected.extend(pool[:open_slots])
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
    _prune_finished_lines(state)
    with state.lock:
        state.calling_window_timer = None
        rules.clear_stale_active(state)
        prospect_lines = [
            call for call in state.in_flight.values() if call.get("kind") == "prospect"
        ]
        should_fill = (
            state.running and not state.paused and state.agent_ready
            and not state.active and not state.pending_outcome
            and len(prospect_lines) < len(state.callers)
        )
    if should_fill:
        fill_slots(state)
    else:
        _schedule_calling_window_check(state)
