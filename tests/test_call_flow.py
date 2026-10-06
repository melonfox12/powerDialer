import base64
import hashlib
import hmac
import json
import tempfile
import unittest
import urllib.parse

from tests.local_server import LocalServers

AUTH_TOKEN = "test-auth-token"
PUBLIC_BASE = "https://hooks.test"


class ImmediateThread:
    def __init__(self, group=None, target=None, name=None, args=(), kwargs=None, *, daemon=None):
        self._target = target
        self._args = args or ()
        self._kwargs = dict(kwargs or {})
        self.daemon = daemon
        self.name = name

    def start(self):
        if self._target is not None:
            self._target(*self._args, **self._kwargs)


class IdleTimer:
    def __init__(self, interval, function, args=None, kwargs=None):
        self.interval = interval
        self.function = function
        self.args = args or ()
        self.kwargs = kwargs or {}
        self.daemon = False

    def start(self):
        return None

    def cancel(self):
        return None


class _ThreadNamespace:
    def __init__(self, real):
        self._real = real
        self.Thread = ImmediateThread
        self.Timer = IdleTimer

    def __getattr__(self, name):
        return getattr(self._real, name)


def sign(url, params, token):
    signed = url
    for key in sorted(params):
        values = params[key]
        if not isinstance(values, (list, tuple)):
            values = [values]
        for value in sorted(str(item) for item in values):
            signed += key + value
    digest = hmac.new(token.encode(), signed.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode()


def fake_twilio(account_sid, auth_token, method, path, data=None, params=None):
    if path.startswith("/IncomingPhoneNumbers"):
        return {
            "incoming_phone_numbers": [
                {"phone_number": "+15551230000", "capabilities": {"voice": True}},
            ],
        }
    if path == "/Calls.json" and method == "POST":
        fake_twilio.calls += 1
        return {"sid": f"CA{fake_twilio.calls:032d}"}
    if method == "POST" and path.startswith("/Calls/"):
        return {}
    raise AssertionError(f"unexpected Twilio request {method} {path}")


fake_twilio.calls = 0


class CallFlowTests(unittest.TestCase):
    def setUp(self):
        import features._dialer.calls as calls
        import features._dialer.slots as slots
        import features._dialer.timing as timing
        import features._dialer.call_events as call_events
        import features._dialer.queue as queue
        import features._dialer.twilio_api as twilio_api

        self._modules = (call_events, queue, timing, calls, slots)
        self._saved_threading = [module.threading for module in self._modules]
        for module in self._modules:
            module.threading = _ThreadNamespace(module.threading)
        self._saved_twilio = twilio_api.twilio_request
        fake_twilio.calls = 0
        twilio_api.twilio_request = fake_twilio
        self._tmp = tempfile.TemporaryDirectory()
        self.servers = LocalServers(self._tmp.name).start()

    def tearDown(self):
        self.servers.stop()
        self._tmp.cleanup()
        import features._dialer.twilio_api as twilio_api

        twilio_api.twilio_request = self._saved_twilio
        for module, saved in zip(self._modules, self._saved_threading):
            module.threading = saved

    def app(self, method, path, body=None, headers=None):
        return self.servers.request(self.servers.app_base, method, path, body, headers)

    def hook(self, path, form, signature=None):
        encoded = urllib.parse.urlencode(form).encode("utf-8")
        parsed = urllib.parse.parse_qs(encoded.decode("utf-8"), keep_blank_values=True)
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        if signature is not None:
            headers["X-Twilio-Signature"] = signature
        elif signature is False:
            pass
        else:
            headers["X-Twilio-Signature"] = sign(PUBLIC_BASE + path, parsed, AUTH_TOKEN)
        return self.servers.request(self.servers.hook_base, "POST", path, encoded, headers)

    def json_app(self, method, path, payload):
        status, raw, _type = self.app(
            method,
            path,
            json.dumps(payload),
            {"Content-Type": "application/json"},
        )
        return status, json.loads(raw.decode("utf-8"))

    def test_signed_call_flow_and_unsigned_webhook(self):
        status, settings = self.json_app("POST", "/api/settings", {
            "account_sid": "AC" + "1" * 32,
            "auth_token": AUTH_TOKEN,
            "api_key": "SK" + "2" * 32,
            "api_secret": "test-api-secret",
            "twiml_app_sid": "AP" + "3" * 32,
            "public_base_url": PUBLIC_BASE,
            "session_goal": "20",
            "calling_start_hour": "0",
            "calling_end_hour": "24",
        })
        self.assertEqual(status, 200)
        self.assertEqual(settings["public_base_url"], PUBLIC_BASE)

        status, created = self.json_app("POST", "/api/leads", {
            "name": "Ada",
            "business": "Shop",
            "phone": "2025550111",
            "timezone": "Eastern",
        })
        self.assertEqual(status, 200)
        lead_id = created["lead"]["id"]

        status, raw, _type = self.hook(
            "/hooks/voice",
            {"CallToken": "missing", "CallSid": "CA0"},
            signature="",
        )
        self.assertEqual(status, 403)
        self.assertEqual(raw, b"Invalid Twilio signature")

        status, started = self.json_app("POST", "/api/start", {})
        self.assertEqual(status, 200)
        agent_token = started["client_call_token"]
        self.assertTrue(started["running"])
        self.assertFalse(started["agent_ready"])

        status, raw, content_type = self.hook("/hooks/voice", {
            "CallToken": agent_token,
            "CallSid": "CAAGENT",
        })
        self.assertEqual(status, 200)
        self.assertIn("xml", content_type)
        self.assertIn(b"Conference", raw)

        dialer = self.servers.runtime.local.dialer
        prospects = [call for call in dialer.calls.values() if call["kind"] == "prospect"]
        self.assertEqual(len(prospects), 1)
        prospect = prospects[0]
        self.assertEqual(prospect["lead_id"], lead_id)
        self.assertTrue(prospect["call_uuid"])
        token = prospect["token"]

        status, raw, content_type = self.hook(f"/hooks/{token}/answer", {"CallSid": prospect["call_uuid"]})
        self.assertEqual(status, 200)
        self.assertIn("xml", content_type)
        self.assertEqual(prospect["state"], "live")
        self.assertTrue(prospect["picked_up"])

        status, raw, _type = self.hook(f"/hooks/{token}/machine", {"AnsweredBy": "human"})
        self.assertEqual(status, 200)
        self.assertEqual(prospect["answered_by"], "human")

        status, raw, _type = self.hook(
            f"/hooks/{token}/status",
            {"CallStatus": "completed", "CallDuration": "45"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(raw, b"OK")
        self.assertEqual(dialer.pending_outcome, lead_id)

        status, updated = self.json_app("POST", f"/api/leads/{lead_id}/status", {"disposition": "booked"})
        self.assertEqual(status, 200)
        self.assertEqual(updated["lead"]["status"], "booked")
        self.assertIsNone(dialer.pending_outcome)

        status, stopped = self.json_app("POST", "/api/stop", {})
        self.assertEqual(status, 200)
        self.assertFalse(stopped["running"])
        summary = stopped["session_summary"]
        self.assertEqual(summary["meetings_booked"], 1)
        self.assertEqual(summary["dials"], 1)
        self.assertIn("duration_seconds", summary)
        self.assertNotIn("connect_times", summary)
