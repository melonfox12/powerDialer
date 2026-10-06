"""Auto-advance timer. Imports slots, not queue."""

import threading
import time

from features._dialer import slots
from features._dialer import projection


def _schedule_advance(state, delay=None):
    with state.lock:
        if not state.running or state.paused or state.pending_outcome or state.active:
            return
        if state.advance_timer:
            state.advance_timer.cancel()
        seconds = max(0, float(delay if delay is not None else state.settings.get("AUTO_ADVANCE_DELAY_SECONDS", 3)))
        state.advance_at = time.time() + seconds
        state.advance_remaining = seconds
        state.advance_timer = threading.Timer(seconds, _advance_queue, args=(state,))
        state.advance_timer.daemon = True
        state.advance_timer.start()


def _advance_queue(state):
    with state.lock:
        state.advance_timer = None
        state.advance_at = None
        state.advance_remaining = None
        should_fill = state.running and not state.paused and not state.pending_outcome
    if should_fill:
        slots.fill_slots(state)


def advance_now(state):
    with state.lock:
        if not state.advance_timer or not state.running or state.paused:
            raise ValueError("There is no active auto-advance countdown.")
        state.advance_timer.cancel()
        state.advance_timer = None
        state.advance_at = None
        state.advance_remaining = None
    slots.fill_slots(state)
    return projection.public_state(state)
