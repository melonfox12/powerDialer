import threading
import time

class AdvanceTimingMixin:
    def _schedule_advance(self, delay=None):
        with self.lock:
            if not self.running or self.paused or self.pending_outcome or self.active:
                return
            if self.advance_timer:
                self.advance_timer.cancel()
            seconds = max(0, float(delay if delay is not None else self.settings.get("AUTO_ADVANCE_DELAY_SECONDS", 3)))
            self.advance_at = time.time() + seconds
            self.advance_remaining = seconds
            self.advance_timer = threading.Timer(seconds, self._advance_queue)
            self.advance_timer.daemon = True
            self.advance_timer.start()

    def _advance_queue(self):
        with self.lock:
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
            should_fill = self.running and not self.paused and not self.pending_outcome
        if should_fill:
            self.fill_slots()

    def advance_now(self):
        with self.lock:
            if not self.advance_timer or not self.running or self.paused:
                raise ValueError("There is no active auto-advance countdown.")
            self.advance_timer.cancel()
            self.advance_timer = None
            self.advance_at = None
            self.advance_remaining = None
        self.fill_slots()
        return self.public_state()

    def _schedule_calling_window_check(self):
        with self.lock:
            if self.calling_window_timer:
                self.calling_window_timer.cancel()
                self.calling_window_timer = None
            if not self.running or self.paused:
                return
            self.calling_window_timer = threading.Timer(60, self._check_calling_window)
            self.calling_window_timer.daemon = True
            self.calling_window_timer.start()

    def _check_calling_window(self):
        with self.lock:
            self.calling_window_timer = None
            should_fill = self.running and not self.paused and not self.active and not self.pending_outcome
        if should_fill:
            self.fill_slots()
        else:
            self._schedule_calling_window_check()
