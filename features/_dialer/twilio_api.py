"""Twilio REST, TwiML helpers, webhook signature, and the call-token index."""

from features.settings import values as _values
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

import base64
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}"

class TwilioError(Exception):
    pass

def twilio_request(account_sid, auth_token, method, path, data=None, params=None):
    url = TWILIO_API.format(account_sid=urllib.parse.quote(account_sid, safe="")) + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    auth = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request.add_header("Authorization", "Basic " + auth)
    if body is not None:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = response.read().decode()
            return json.loads(result) if result else {}
    except urllib.error.HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode())
            message = payload.get("message") or payload.get("error") or str(exc)
        except (ValueError, OSError):
            message = str(exc)
        raise TwilioError(f"Twilio error {exc.code}: {message}") from exc
    except urllib.error.URLError as exc:
        raise TwilioError(f"Could not reach Twilio: {exc.reason}") from exc

def normalize_phone(raw):
    text = str(raw or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None

def escape_xml(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;"))

import threading

class TokenIndex:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens = {}

    def register(self, token, dialer):
        with self._lock:
            self._tokens[token] = dialer

    def forget(self, token):
        with self._lock:
            self._tokens.pop(token, None)

    def lookup(self, token):
        if not token:
            return None
        with self._lock:
            return self._tokens.get(token)

def validate_webhook(state, url, signature, params):
    values = state.settings or _values(state.env_path, state.account_values)
    auth_token = values.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token or not signature:
        return False
    signed = url
    for key in sorted(params):
        values = params[key]
        if not isinstance(values, (list, tuple)):
            values = [values]
        for value in sorted(str(value) for value in values):
            signed += key + value
    digest = hmac.new(auth_token.encode(), signed.encode(), hashlib.sha1).digest()
    expected = base64.b64encode(digest).decode()
    return hmac.compare_digest(expected, signature)

def _url(state, call, action):
    return f"{state.public_base_url}/hooks/{call['token']}/{action}"

def _hangup_call(state, call_uuid):
    try:
        twilio_request(state.settings["TWILIO_ACCOUNT_SID"], state.settings["TWILIO_AUTH_TOKEN"], "POST",
                       f"/Calls/{urllib.parse.quote(call_uuid, safe='')}.json", data={"Status": "completed"})
    except (TwilioError, KeyError):
        pass

def voice_access_token(state):
    state.record_activity("Requesting browser Voice access token", "api")
    values = _values(state.env_path, state.account_values)
    required = (
        "TWILIO_ACCOUNT_SID", "TWILIO_API_KEY", "TWILIO_API_SECRET",
        "TWILIO_TWIML_APP_SID",
    )
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise ValueError("Complete Twilio Account SID, API Key SID, API Key Secret, and TwiML App SID in Settings.")
    token = AccessToken(
        values["TWILIO_ACCOUNT_SID"],
        values["TWILIO_API_KEY"],
        values["TWILIO_API_SECRET"],
        identity="prospect_desk_agent",
        ttl=3600,
    )
    token.add_grant(VoiceGrant(outgoing_application_sid=values["TWILIO_TWIML_APP_SID"]))
    return token.to_jwt()

