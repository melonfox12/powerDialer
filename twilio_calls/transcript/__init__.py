from twilio_calls.transcript.ended import EndedMixin
from twilio_calls.transcript.live import LiveMixin


class TranscriptMixin(EndedMixin, LiveMixin):
    pass
