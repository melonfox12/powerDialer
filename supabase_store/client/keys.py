from twilio_calls.settings import DIALER_DEFAULTS

METRIC_KEYS = {
    "booked", "call_later", "connected", "disqualified", "interested", "dials",
    "failed", "talk_seconds", "voicemail",
}

SETTINGS_ROW_ID = "app"

REMOTE_SETTING_KEYS = (
    "TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_API_KEY",
    "TWILIO_API_SECRET", "TWILIO_TWIML_APP_SID", "PUBLIC_BASE_URL",
    *DIALER_DEFAULTS.keys(),
)
