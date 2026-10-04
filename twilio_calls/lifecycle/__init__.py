from twilio_calls.lifecycle.controls import ControlsMixin
from twilio_calls.lifecycle.outcome import OutcomeMixin
from twilio_calls.lifecycle.queue import QueueMixin


class LifecycleMixin(ControlsMixin, QueueMixin, OutcomeMixin):
    pass
