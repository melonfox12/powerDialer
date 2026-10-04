from twilio_calls.client import ClientMixin
from twilio_calls.dialer.core import CoreMixin
from twilio_calls.dialer.state import StateMixin
from twilio_calls.lifecycle import LifecycleMixin
from twilio_calls.settings import SettingsMixin
from twilio_calls.token import TokenMixin
from twilio_calls.transcript import TranscriptMixin
from twilio_calls.webhooks import WebhookMixin


class TwilioDialer(CoreMixin, StateMixin, SettingsMixin, ClientMixin, TokenMixin, WebhookMixin, TranscriptMixin, LifecycleMixin):
    pass
