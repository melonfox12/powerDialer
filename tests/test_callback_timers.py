import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from features._dialer import calls, queue
from features._dialer._call_events import ended
from features.dialer import Dialer
from features.metrics import MetricsStore
from features.prospects import ProspectStore
from shared.infra import utc_now
from shared.vocabulary import MANUAL_CALLBACK_HOURS, NO_PICKUP_CALLBACK_HOURS


def _lead(lead_id, phone="+12025550101", name="Ada"):
    return {"id": lead_id, "name": name, "phone": phone, "status": "new", "call_log": []}


class CallbackTimerTests(unittest.TestCase):
    def test_no_pickup_callback_is_two_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            queue.schedule_no_pickup_callback(dialer, "a")
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            remaining = calls._callback_due(lead) - utc_now()
            self.assertGreater(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS) - timedelta(seconds=5))
            self.assertLessEqual(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS))

    def test_manual_callback_is_two_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            queue.schedule_callback(dialer, "a")
            lead = crm.snapshot()[0]
            remaining = calls._callback_due(lead) - utc_now()
            self.assertGreater(remaining, timedelta(hours=MANUAL_CALLBACK_HOURS) - timedelta(seconds=5))
            self.assertLessEqual(remaining, timedelta(hours=MANUAL_CALLBACK_HOURS))

    def test_no_pickup_callback_applies_to_send_info(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{**_lead("a"), "status": "send_info"}]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            queue.schedule_no_pickup_callback(dialer, "a")
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            self.assertTrue(lead["scheduled_until"])

    def test_unconnected_callback_even_while_session_paused(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            dialer.running = True
            dialer.paused = True
            dialer.active = {"lead_id": "other"}
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["call_uuid"] = "CA-x"
            ended._call_ended(dialer, call, {"CallStatus": "no-answer", "CallDuration": "0"})
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            self.assertTrue(lead["scheduled_until"])

    def test_no_pickup_does_not_override_an_existing_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            manual = crm.set_status("a", "call", (utc_now() + timedelta(hours=MANUAL_CALLBACK_HOURS)).isoformat())
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            self.assertIsNone(queue.schedule_no_pickup_callback(dialer, "a"))
            self.assertEqual(crm.snapshot()[0]["scheduled_until"], manual["scheduled_until"])

    def test_backfill_new_leads_with_unpicked_dials(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{
                **_lead("a"),
                "call_log": [{
                    "id": "dial-1",
                    "started_at": utc_now().isoformat(),
                    "ended_at": utc_now().isoformat(),
                    "answered_by": "no_answer",
                    "connected": False,
                }],
            }]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            self.assertEqual(queue.sync_new_unpicked_dial_callbacks(dialer), 1)
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            self.assertTrue(lead["scheduled_until"])

    def test_backfill_skips_when_call_log_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            self.assertEqual(queue.sync_new_unpicked_dial_callbacks(dialer), 0)

    def test_backfill_skips_disqualified(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{
                **_lead("a"),
                "status": "disqualified",
                "call_log": [{
                    "id": "dial-1",
                    "started_at": utc_now().isoformat(),
                    "ended_at": utc_now().isoformat(),
                    "answered_by": "no_answer",
                    "connected": False,
                }],
            }]
            crm.save()
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            self.assertEqual(queue.sync_new_unpicked_dial_callbacks(dialer), 0)

    def test_legacy_forty_eight_hour_callback_shifts_forward_once(self):
        with tempfile.TemporaryDirectory() as directory:
            due = utc_now() + timedelta(hours=47)
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{
                "id": "a",
                "name": "Ada",
                "phone": "+12025550101",
                "status": "call",
                "scheduled_until": due.isoformat(),
                "call_log": [],
                "fields": {},
            }]
            crm.save()
            crm = ProspectStore(Path(directory) / "crm")
            lead = crm.snapshot()[0]
            remaining = calls._callback_due(lead) - utc_now()
            self.assertGreater(remaining, timedelta(minutes=30))
            self.assertLessEqual(remaining, timedelta(hours=2))
            self.assertTrue(lead["fields"].get("callback_timer_48h_to_2h"))


if __name__ == "__main__":
    unittest.main()
