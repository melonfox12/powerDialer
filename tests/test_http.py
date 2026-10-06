import json
import tempfile
import unittest
from pathlib import Path

from tests.local_server import LocalServers

ROOT = Path(__file__).resolve().parent.parent

STATE_KEYS = (
    "active_call_started_at",
    "active_lead",
    "active_lead_id",
    "activity_log",
    "advance_at",
    "agent_ready",
    "caller_ids",
    "counts",
    "current_caller_id",
    "in_flight",
    "last_error",
    "last_event",
    "leads",
    "leads_version",
    "live_transcript",
    "manual_lead_id",
    "next_lead",
    "paused",
    "pending_outcome",
    "pending_outcome_id",
    "pickup_answered_by",
    "pool",
    "queue_count",
    "running",
    "selected_timezone",
    "session_stats",
    "settings",
    "stage",
    "timezone_groups",
)

LIVE_KEYS = tuple(key for key in STATE_KEYS if key not in ("leads", "pool"))

SETTINGS_KEYS = (
    "account_email",
    "account_sid",
    "api_key",
    "api_secret",
    "auth_token",
    "auto_advance_delay",
    "break_nudge_minutes",
    "calling_end_hour",
    "calling_start_hour",
    "conversation_threshold",
    "has_api_secret",
    "has_auth_token",
    "opening_script",
    "public_base_url",
    "session_goal",
    "sound_volume",
    "sounds_enabled",
    "storage",
    "twiml_app_sid",
)

DAILY_METRIC_KEYS = ("booked", "connected", "date", "dials")


class HttpContractTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.servers = LocalServers(self._tmp.name).start()
        self.assertEqual(self.servers.runtime.storage_name, "local JSON files")

    def tearDown(self):
        self.servers.stop()
        self._tmp.cleanup()

    def request(self, method, path, body=None, headers=None):
        return self.servers.request(self.servers.app_base, method, path, body, headers)

    def json_request(self, method, path, payload=None):
        body = None if payload is None else json.dumps(payload)
        headers = {"Content-Type": "application/json"} if body is not None else None
        status, raw, content_type = self.request(method, path, body, headers)
        data = json.loads(raw.decode("utf-8")) if raw else None
        return status, data, content_type

    def assert_keys(self, payload, keys):
        self.assertEqual(tuple(sorted(payload)), tuple(sorted(keys)))

    def test_endpoint_status_and_top_level_keys(self):
        status, page, content_type = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", content_type)
        snapshot = ROOT / "docs" / "page-before.html"
        if not snapshot.exists():
            snapshot.write_bytes(page)
        def comparable(body):
            text = body.replace(b"\r\n", b"\n")
            text = text.replace(
                b'<button id="enterLiveButton" class="button button-secondary monitor-enter-live" type="button" hidden>Enter live line</button>',
                b"",
            )
            start = text.find(b'<script type="application/json" id="vocabulary">')
            if start != -1:
                end = text.find(b"</script>", start)
                text = text[:start] + text[end + len(b"</script>"):]
            return text
        self.assertEqual(comparable(page), comparable(snapshot.read_bytes()))

        status, raw, content_type = self.request("GET", "/css/01-tokens.css")
        self.assertEqual(status, 200)
        self.assertIn("text/css", content_type)
        status, raw, content_type = self.request("GET", "/js/main.js")
        self.assertEqual(status, 200)
        self.assertIn("javascript", content_type)

        status, payload, _type = self.json_request("GET", "/api/auth/config")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"google": False, "url": "", "anonKey": ""})

        status, payload, _type = self.json_request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"ok": True, "storage": "local JSON files"})

        status, payload, _type = self.json_request("GET", "/api/auth/me")
        self.assertEqual(status, 200)
        self.assertEqual(payload, {"id": "", "email": ""})

        status, payload, _type = self.json_request("GET", "/api/state")
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)

        status, payload, _type = self.json_request("GET", "/api/live")
        self.assertEqual(status, 200)
        self.assert_keys(payload, LIVE_KEYS)

        status, payload, _type = self.json_request("GET", "/api/metrics")
        self.assertEqual(status, 200)
        self.assert_keys(payload, ("all_time", "daily", "today"))
        self.assertEqual(payload["today"], {})
        self.assertEqual(payload["all_time"], {})
        self.assertEqual(len(payload["daily"]), 7)
        for day in payload["daily"]:
            self.assert_keys(day, DAILY_METRIC_KEYS)

        status, payload, _type = self.json_request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assert_keys(payload, SETTINGS_KEYS)

        status, payload, _type = self.json_request("GET", "/api/voice-token")
        self.assertEqual(status, 400)
        self.assert_keys(payload, ("error",))

        status, raw, content_type = self.request("GET", "/api/export.csv")
        self.assertEqual(status, 200)
        self.assertIn("text/csv", content_type)
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))

        status, raw, _type = self.request(
            "POST",
            "/api/debug",
            json.dumps({"level": "client", "message": "clicked start"}),
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 204)
        self.assertEqual(raw, b"")

        status, raw, _type = self.request("POST", "/api/debug", b"{}", {"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        self.assertEqual(raw, b"")

        status, payload, _type = self.json_request("POST", "/api/leads", {
            "name": "Ada",
            "business": "Shop",
            "phone": "2025550111",
            "timezone": "Eastern",
        })
        self.assertEqual(status, 200)
        self.assert_keys(payload, ("lead", "state"))
        self.assert_keys(payload["state"], STATE_KEYS)
        lead_id = payload["lead"]["id"]

        csv_body = b"Name,Phone,Timezone\nBea,2025550112,Central\n"
        status, raw, content_type = self.request(
            "POST", "/api/import", csv_body, {"Content-Type": "text/csv"},
        )
        payload = json.loads(raw.decode("utf-8"))
        self.assertEqual(status, 200)
        self.assert_keys(payload, ("import", "state"))
        self.assert_keys(payload["import"], ("added", "columns", "duplicates", "skipped", "total"))
        self.assert_keys(payload["state"], STATE_KEYS)

        status, payload, _type = self.json_request("POST", "/api/settings", {
            "session_goal": "20",
            "calling_start_hour": "8",
            "calling_end_hour": "21",
        })
        self.assertEqual(status, 200)
        self.assert_keys(payload, SETTINGS_KEYS)

        status, payload, _type = self.json_request("POST", "/api/timezone", {"timezone": "Eastern"})
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)

        status, payload, _type = self.json_request("POST", "/api/start", {})
        self.assertEqual(status, 400)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", "/api/pause", {})
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)

        status, payload, _type = self.json_request("POST", "/api/stop", {})
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)

        status, payload, _type = self.json_request("POST", "/api/hangup", {})
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)

        status, payload, _type = self.json_request("POST", "/api/skip", {})
        self.assertEqual(status, 400)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", "/api/enter-live", {})
        self.assertEqual(status, 404)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", "/api/advance", {})
        self.assertEqual(status, 400)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", f"/api/leads/{lead_id}/dial", {})
        self.assertEqual(status, 400)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", f"/api/leads/{lead_id}/status", {"status": "interested"})
        self.assertEqual(status, 200)
        self.assert_keys(payload, ("lead", "state"))
        self.assert_keys(payload["state"], STATE_KEYS)

        status, payload, _type = self.json_request("GET", "/api/missing")
        self.assertEqual(status, 404)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("POST", "/api/missing", {})
        self.assertEqual(status, 404)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("DELETE", "/api/missing")
        self.assertEqual(status, 404)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("DELETE", "/api/leads/missing-lead")
        self.assertEqual(status, 404)
        self.assert_keys(payload, ("error",))

        status, payload, _type = self.json_request("DELETE", f"/api/leads/{lead_id}")
        self.assertEqual(status, 200)
        self.assert_keys(payload, STATE_KEYS)
