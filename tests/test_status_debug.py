import json
import tempfile
import unittest

from tests.local_server import LocalServers


class StatusUpdateDebugTests(unittest.TestCase):
    def test_sunstate_like_lead_accepts_crm_statuses(self):
        with tempfile.TemporaryDirectory() as directory:
            servers = LocalServers(directory).start()
            try:
                base = servers.app_base
                lead = {
                    "id": "sunstate-1",
                    "name": "Sunstate Pest Control",
                    "business": "Sunstate",
                    "phone": "+12025550999",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                    "call_log": [
                        {
                            "id": "d1",
                            "started_at": "2026-01-01T12:00:00+00:00",
                            "ended_at": "2026-01-01T12:01:00+00:00",
                            "answered_by": "human",
                        },
                        {
                            "id": "d2",
                            "started_at": "2026-01-02T12:00:00+00:00",
                            "ended_at": "2026-01-02T12:01:00+00:00",
                            "answered_by": "no_answer",
                        },
                    ],
                }
                crm = servers.runtime.local.crm
                crm.leads = [lead]
                crm.save()

                def post_status(payload):
                    body = json.dumps(payload).encode("utf-8")
                    status, raw, _content = servers.request(
                        base,
                        "POST",
                        "/api/leads/sunstate-1/status",
                        body,
                        {"Content-Type": "application/json"},
                    )
                    data = json.loads(raw.decode("utf-8")) if raw else {}
                    return status, data

                lead["call_log"] = []
                crm.leads = [lead]
                crm.save()

                for key in ("new", "call", "send_info", "booked", "disqualified", "no_answer_disqualified"):
                    code, data = post_status({"status": key})
                    self.assertEqual(code, 200, (key, data))
                    self.assertEqual(data["lead"]["status"], key, key)

                lead["status"] = "new"
                lead["scheduled_until"] = None
                crm.leads = [lead]
                crm.save()
                code, data = post_status({"status": "Send info"})
                self.assertEqual(code, 200, data)
                self.assertEqual(data["lead"]["status"], "send_info")

                code, data = post_status({})
                self.assertEqual(code, 200, data)
                self.assertEqual(data["lead"]["status"], "send_info")

                lead["call_log"] = [
                    {"id": "d1", "started_at": "2026-01-01T12:00:00+00:00", "ended_at": "2026-01-01T12:01:00+00:00"},
                    {"id": "d2", "started_at": "2026-01-02T12:00:00+00:00", "ended_at": "2026-01-02T12:01:00+00:00"},
                    {"id": "d3", "started_at": "2026-01-03T12:00:00+00:00", "ended_at": "2026-01-03T12:01:00+00:00"},
                    {"id": "d4", "started_at": "2026-01-04T12:00:00+00:00", "ended_at": "2026-01-04T12:01:00+00:00"},
                    {"id": "d5", "started_at": "2026-01-05T12:00:00+00:00", "ended_at": "2026-01-05T12:01:00+00:00"},
                ]
                crm.leads = [lead]
                crm.save()
                code, data = post_status({"status": "send_info"})
                self.assertEqual(code, 200, data)
                self.assertEqual(data["lead"]["status"], "send_info")
                caps = crm.enforce_dial_caps()
                self.assertEqual(caps["capped"], 1)
                self.assertEqual(crm.snapshot()[0]["status"], "no_answer_disqualified")
            finally:
                servers.stop()


if __name__ == "__main__":
    unittest.main()
