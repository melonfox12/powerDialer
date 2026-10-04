from twilio_calls.token.index import TokenIndex
from twilio_calls.token.start import StartMixin
from twilio_calls.token.voice import VoiceMixin


class TokenMixin(StartMixin, VoiceMixin):
    pass
