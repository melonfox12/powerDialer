import tempfile
from pathlib import Path
from crm_store import CRMStore
from core.dialer_session import new_session
from twilio_calls import TwilioDialer

class Part2:
    def test_callback_is_persisted_and_do_not_call_leaves_the_auto_dial_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1",
                "name": "Onyx Garage Floors",
                "business": "Onyx Garage Floors",
                "phone": "+12025550123",
                "timezone": "Eastern",
                "status": "new",
                "scheduled_until": None,
                "transcript": [],
                "fields": {},
            }
            crm.leads = [lead]
            callback = crm.set_status("prospect-1", "call", "2030-01-02T14:00:00+00:00")
            self.assertEqual(callback["scheduled_until"], "2030-01-02T14:00:00+00:00")
            crm.set_status("prospect-1", "do_not_call")
            self.assertEqual(crm.timezone_groups(), [])
            self.assertEqual(crm.snapshot()[0]["status"], "do_not_call")

    def test_any_pickup_connects_and_a_long_live_call_counts_as_a_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.session = new_session(goal=1)
            dialer.settings = {"CONVERSATION_THRESHOLD_SECONDS": "30"}
            call = dialer._new_call("prospect", lead)
            dialer._pickup(call)
            self.assertEqual(dialer.session["connects"], 1)
            dialer._machine_result(call, {"AnsweredBy": "human"})
            self.assertEqual(dialer.session["connects"], 1)
            self.assertEqual(call["answered_by"], "human")
            dialer._call_ended(call, {"CallDuration": "30"})
            self.assertEqual(dialer.session["conversations"], 1)
            self.assertEqual(dialer.pending_outcome, lead["id"])
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            dialer.choose_outcome(lead["id"], "interested")
            self.assertEqual(crm.snapshot()[0]["status"], "interested")
