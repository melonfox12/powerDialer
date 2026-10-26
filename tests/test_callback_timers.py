import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from features._dialer import calls, queue
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

    def test_no_pickup_does_not_override_an_existing_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            manual = crm.set_status("a", "call", (utc_now() + timedelta(hours=MANUAL_CALLBACK_HOURS)).isoformat())
            dialer = Dialer(crm, str(Path(directory) / ".env"), metrics=MetricsStore(Path(directory) / "metrics.json"))
            self.assertIsNone(queue.schedule_no_pickup_callback(dialer, "a"))
            self.assertEqual(crm.snapshot()[0]["scheduled_until"], manual["scheduled_until"])

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
