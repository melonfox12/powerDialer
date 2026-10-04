from twilio_calls.webhooks.dispatch import DispatchMixin
from twilio_calls.webhooks.live import LiveMixin
from twilio_calls.webhooks.pickup import PickupMixin


class WebhookMixin(DispatchMixin, PickupMixin, LiveMixin):
    pass
