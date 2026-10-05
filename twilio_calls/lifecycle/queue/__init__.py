from twilio_calls.lifecycle.queue.manual import ManualDialMixin
from twilio_calls.lifecycle.queue.slots import SlotMixin
from twilio_calls.lifecycle.queue.timing import AdvanceTimingMixin


class QueueMixin(ManualDialMixin, SlotMixin, AdvanceTimingMixin):
    pass
