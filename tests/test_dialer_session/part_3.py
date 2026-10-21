import tempfile
from pathlib import Path
from features.prospects import ProspectStore
from features._dialer.rules import new_session
from features.dialer import Dialer

class Part3:
    def test_answer_waits_for_a_person_and_voicemail_frees_only_that_line(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            first = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            second = {
                "id": "prospect-2", "name": "Ada", "business": "Ada",
                "phone": "+12025550124", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [first, second]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.public_base_url = "https://example.test"
            dialer.conference = "crm-test"
            dialer.settings = {"TWILIO_ACCOUNT_SID": "ACexample", "TWILIO_AUTH_TOKEN": "token"}
            dialer.save_settings({"session_goal": 20})
            dialer.running = True
            dialer.session = new_session()
            machine = dialer._new_call("prospect", first)
            machine["call_uuid"] = "CA-machine"
            person = dialer._new_call("prospect", second)
            person["call_uuid"] = "CA-person"
            person["caller_id"] = "+15551230001"

            status, _, twiml = dialer.handle_webhook(machine["token"], "answer", {"CallSid": "CA-machine"})
            self.assertEqual(status, 200)
            self.assertIn("<Pause", twiml)
            self.assertNotIn("<Conference", twiml)
            self.assertIsNone(dialer.active)
            self.assertFalse(machine.get("picked_up"))

            dialer._machine_result(machine, {"AnsweredBy": "machine_end_beep"})
            self.assertEqual(machine["answered_by"], "voicemail")
            self.assertTrue(machine["skip_closed"])
            self.assertIsNone(dialer.active)
            self.assertIn(person["token"], dialer.in_flight)
            self.assertEqual(crm.snapshot()[0]["status"], "call")

            status, _, twiml = dialer.handle_webhook(person["token"], "machine", {"AnsweredBy": "human", "CallSid": "CA-person"})
            self.assertEqual(status, 200)
            self.assertTrue(person["picked_up"])
            self.assertIs(dialer.active, person)
            self.assertEqual(dialer.public_state()["live_transcript"]["lead_id"], second["id"])
            self.assertEqual(dialer.public_state()["current_caller_id"], "+15551230001")
            status, _, twiml = dialer.handle_webhook(person["token"], "answer", {"CallSid": "CA-person"})
            self.assertIn("<Conference", twiml)
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_unanswered_call_is_kept_in_the_dial_log(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Marillian", "business": "Buono Pest Control",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-miss"
            status, _, _ = dialer.handle_webhook(call["token"], "status", {"CallSid": "CA-miss", "CallStatus": "no-answer"})
            self.assertEqual(status, 200)
            saved = crm.snapshot()[0]["call_log"]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["id"], "CA-miss")
            self.assertEqual(saved[0]["answered_by"], "no_answer")
            self.assertTrue(saved[0]["started_at"])
            self.assertIsNotNone(dialer.advance_timer)
            self.assertTrue(crm.snapshot()[0]["passed_at"])
            dialer.advance_timer.cancel()
