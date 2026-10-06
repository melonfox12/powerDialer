"""Auto-advance and calling-window timers."""

import threading
import time

from features._dialer._queue import slots

def _schedule_advance(state, delay=None):
    with state.lock:
        if not state.running or state.paused or state.pending_outcome or state.active:
            return
        if state.advance_timer:
            state.advance_timer.cancel()
        seconds = max(0, float(delay if delay is not None else state.settings.get("AUTO_ADVANCE_DELAY_SECONDS", 3)))
        state.advance_at = time.time() + seconds
        state.advance_remaining = seconds
        state.advance_timer = threading.Timer(seconds, state._advance_queue)
        state.advance_timer.daemon = True
        state.advance_timer.start()

def _advance_queue(state):
    with state.lock:
        state.advance_timer = None
        state.advance_at = None
        state.advance_remaining = None
        should_fill = state.running and not state.paused and not state.pending_outcome
    if should_fill:
        state.fill_slots()

def advance_now(state):
    with state.lock:
        if not state.advance_timer or not state.running or state.paused:
            raise ValueError("There is no active auto-advance countdown.")
        state.advance_timer.cancel()
        state.advance_timer = None
        state.advance_at = None
        state.advance_remaining = None
    state.fill_slots()
    return state.public_state()

def _schedule_calling_window_check(state):
    with state.lock:
        if state.calling_window_timer:
            state.calling_window_timer.cancel()
            state.calling_window_timer = None
        if not state.running or state.paused:
            return
        state.calling_window_timer = threading.Timer(60, state._check_calling_window)
        state.calling_window_timer.daemon = True
        state.calling_window_timer.start()

def _check_calling_window(state):
    with state.lock:
        state.calling_window_timer = None
        should_fill = state.running and not state.paused and not state.active and not state.pending_outcome
    if should_fill:
        state.fill_slots()
    else:
        state._schedule_calling_window_check()
