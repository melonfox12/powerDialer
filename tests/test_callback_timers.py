import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from features._dialer._call_events import ended
from features.dialer import Dialer
from features.metrics import MetricsStore
from features.prospects import ProspectStore
from shared.dial_policy import apply_total_dials_callback_status
from shared.infra import utc_now
from shared.vocabulary import MANUAL_CALLBACK_HOURS, NO_PICKUP_CALLBACK_HOURS


def _lead(lead_id, phone="+12025550101", name="Ada"):
    return {"id": lead_id, "name": name, "phone": phone, "status": "new", "call_log": []}


class CallbackTimerTests(unittest.TestCase):
    def test_total_dials_row_sets_callback_from_new(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            crm.append_call_log("a", {
                "id": "dial-1",
                "started_at": utc_now().isoformat(),
                "ended_at": "",
                "answered_by": "no_answer",
                "connected": False,
            })
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            remaining = datetime.fromisoformat(lead["scheduled_until"]) - utc_now()
            self.assertGreater(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS) - timedelta(seconds=5))
            self.assertLessEqual(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS))

    def test_total_dials_row_keeps_send_info(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{**_lead("a"), "status": "send_info"}]
            crm.save()
            crm.append_call_log("a", {
                "id": "dial-1",
                "started_at": utc_now().isoformat(),
                "answered_by": "no_answer",
                "connected": False,
            })
            self.assertEqual(crm.snapshot()[0]["status"], "send_info")

    def test_total_dials_row_skips_connected_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            crm.append_call_log("a", {
                "id": "dial-1",
                "started_at": utc_now().isoformat(),
                "answered_by": "human",
                "connected": True,
            })
            self.assertEqual(crm.snapshot()[0]["status"], "new")

    def test_unconnected_call_end_uses_call_log_rule(self):
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

    def test_active_callback_is_not_reset_by_another_dial_row(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            manual = crm.set_status("a", "call", (utc_now() + timedelta(hours=MANUAL_CALLBACK_HOURS)).isoformat())
            crm.append_call_log("a", {
                "id": "dial-2",
                "started_at": utc_now().isoformat(),
                "answered_by": "no_answer",
                "connected": False,
            })
            self.assertEqual(crm.snapshot()[0]["scheduled_until"], manual["scheduled_until"])

    def test_repair_new_leads_with_dial_log(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            with crm.lock:
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
            self.assertEqual(crm.repair_total_dials_callbacks(), 1)
            lead = crm.snapshot()[0]
            self.assertEqual(lead["status"], "call")
            self.assertTrue(lead["scheduled_until"])

    def test_repair_skips_without_call_log(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [_lead("a")]
            crm.save()
            self.assertEqual(crm.repair_total_dials_callbacks(), 0)

    def test_repair_skips_disqualified(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm")
            crm.leads = [{
                **_lead("a"),
                "status": "disqualified",
                "call_log": [{
                    "id": "dial-1",
                    "started_at": utc_now().isoformat(),
                    "answered_by": "no_answer",
                }],
            }]
            crm.save()
            self.assertEqual(crm.repair_total_dials_callbacks(), 0)

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
            from features._dialer import calls
            remaining = calls._callback_due(lead) - utc_now()
            self.assertGreater(remaining, timedelta(minutes=30))
            self.assertLessEqual(remaining, timedelta(hours=2))
            self.assertTrue(lead["fields"].get("callback_timer_48h_to_2h"))

    def test_apply_total_dials_callback_status_unit(self):
        lead = _lead("x")
        self.assertTrue(apply_total_dials_callback_status(lead, {"connected": False}))
        self.assertEqual(lead["status"], "call")


if __name__ == "__main__":
    unittest.main()
