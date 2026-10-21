"""Twilio REST, TwiML helpers, webhook signature, and the call-token index."""

from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant

import base64
import hashlib
import hmac
import json
import math
import struct
import urllib.error
import urllib.parse
import urllib.request

TWILIO_API = "https://api.twilio.com/2010-04-01/Accounts/{account_sid}"

class TwilioError(Exception):
    pass

def twilio_request(account_sid, auth_token, method, path, data=None, params=None, username=None):
    url = TWILIO_API.format(account_sid=urllib.parse.quote(account_sid, safe="")) + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    body = urllib.parse.urlencode(data, doseq=True).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, method=method)
    auth = base64.b64encode(f"{username or account_sid}:{auth_token}".encode()).decode()
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

def waiting_twiml(state):
    """Ring the answered line until Twilio decides a person is there."""
    url = escape_xml(f"{state.public_base_url}/hooks/ringback.wav")
    return f'<Response><Play loop="3">{url}</Play></Response>'

def ringback_wav():
    """Two seconds of ring, then four seconds of quiet. One North American ring cycle."""
    global _RINGBACK
    if _RINGBACK is None:
        rate = 8000
        frames = bytearray()
        for index in range(rate * 2):
            second = index / rate
            sample = 0.35 * (math.sin(2 * math.pi * 440 * second) + math.sin(2 * math.pi * 480 * second))
            frames += struct.pack("<h", int(sample * 32767))
        frames += b"\x00\x00" * (rate * 4)
        _RINGBACK = struct.pack(
            "<4sI4s4sIHHIIHH4sI",
            b"RIFF", 36 + len(frames), b"WAVE", b"fmt ", 16, 1, 1, rate, rate * 2, 2, 16, b"data", len(frames),
        ) + bytes(frames)
    return _RINGBACK

_RINGBACK = None

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
    stored = state.settings or state.read_values()
    auth_token = stored.get("TWILIO_AUTH_TOKEN", "")
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

def _start_live_transcription(state, call_uuid, callback_url, name):
    """Start another live transcript on a call that is still connected."""
    if not call_uuid or not callback_url or not name:
        return
    twilio_request(state.settings["TWILIO_ACCOUNT_SID"], state.settings["TWILIO_AUTH_TOKEN"], "POST",
                   f"/Calls/{urllib.parse.quote(call_uuid, safe='')}/Transcriptions.json",
                   data={
                       "Name": name,
                       "Track": "both_tracks",
                       "StatusCallbackUrl": callback_url,
                       "StatusCallbackMethod": "POST",
                       "InboundTrackLabel": "prospect",
                       "OutboundTrackLabel": "agent",
                       "PartialResults": "true",
                       "LanguageCode": "en-US",
                       "SpeechModel": "telephony",
                       "EnableAutomaticPunctuation": "true",
                   })

def _redirect_call(state, call_uuid, url):
    """Point an answered call at new TwiML once we know a person is on the line."""
    if not call_uuid or not url:
        return
    try:
        twilio_request(state.settings["TWILIO_ACCOUNT_SID"], state.settings["TWILIO_AUTH_TOKEN"], "POST",
                       f"/Calls/{urllib.parse.quote(call_uuid, safe='')}.json",
                       data={"Url": url, "Method": "POST"})
    except (TwilioError, KeyError):
        pass

def prepare_browser_voice(state, values):
    """Check the API key, then point the TwiML app at this dialer's voice URL."""
    account = values["TWILIO_ACCOUNT_SID"]
    token = values["TWILIO_AUTH_TOKEN"]
    if not _api_key_accepted(account, values["TWILIO_API_KEY"], values["TWILIO_API_SECRET"]):
        raise TwilioError(
            "The API Key Secret does not match the API Key SID. Paste the current secret in Settings and click Save. The saved secret was not changed."
        )
    voice_url = f"{state.public_base_url}/hooks/voice"
    _point_voice_app(state, account, token, values["TWILIO_TWIML_APP_SID"], voice_url)


def _api_key_accepted(account, key, secret):
    try:
        twilio_request(account, secret, "GET", ".json", username=key)
    except TwilioError as exc:
        message = str(exc)
        if "permissions" in message.lower():
            return True
        if "Twilio error 401" in message:
            return False
        raise
    return True


def _point_voice_app(state, account, token, app_sid, voice_url):
    path = "/Applications/" + urllib.parse.quote(app_sid, safe="") + ".json"
    try:
        app = twilio_request(account, token, "GET", path)
    except TwilioError as exc:
        if "Twilio error 404" in str(exc):
            raise TwilioError("The TwiML App SID in Settings was not found on this Twilio account.") from exc
        raise
    current = str(app.get("voice_url") or "").rstrip("/")
    method = str(app.get("voice_method") or "").upper()
    if current == voice_url and method == "POST":
        return
    twilio_request(account, token, "POST", path, data={"VoiceUrl": voice_url, "VoiceMethod": "POST"})
    state.record_activity("Pointed the TwiML app at the public voice URL", "api")


def voice_access_token(state):
    state.record_activity("Requesting browser Voice access token", "api")
    values = state.read_values()
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

