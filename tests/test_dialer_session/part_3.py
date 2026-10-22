import tempfile
from datetime import timedelta
from pathlib import Path
from features.prospects import ProspectStore
from features._dialer import calls
from features._dialer.rules import new_session
from features.dialer import Dialer
from shared.infra import utc_now

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
            self.assertNotIn("<Play", twiml)
            self.assertNotIn("<Conference", twiml)
            self.assertIsNone(dialer.active)
            self.assertFalse(machine.get("picked_up"))

            dialer._machine_result(machine, {"AnsweredBy": "machine_end_beep"})
            self.assertEqual(machine["answered_by"], "voicemail")
            self.assertTrue(machine["skip_closed"])
            self.assertIsNone(dialer.active)
            self.assertIn(person["token"], dialer.in_flight)
            # Voicemail stays in the queue and waits out its retry window. No callback, one log entry.
            first_after = crm.snapshot()[0]
            self.assertEqual(first_after["status"], "new")
            self.assertEqual([item["answered_by"] for item in first_after["call_log"]], ["voicemail"])
            self.assertEqual(first_after["call_log"][0]["id"], "CA-machine")

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

    def _dialer_with_leads(self, directory, count):
        crm = ProspectStore(Path(directory) / "crm.json")
        crm.leads = [
            {
                "id": f"prospect-{index}", "name": f"Lead {index}", "business": "Shop",
                "phone": f"+1202555010{index}", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            for index in range(count)
        ]
        dialer = Dialer(crm, str(Path(directory) / ".env"))
        dialer.public_base_url = "https://example.test"
        dialer.conference = "crm-test"
        dialer.settings = {"TWILIO_ACCOUNT_SID": "ACexample", "TWILIO_AUTH_TOKEN": "token"}
        dialer.running = True
        dialer.session = new_session()
        return crm, dialer

    def test_a_line_that_loses_the_race_stays_in_the_queue_and_is_logged_once(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            person = dialer._new_call("prospect", leads[0])
            loser = dialer._new_call("prospect", leads[1])

            dialer._machine_result(person, {"AnsweredBy": "human"})
            self.assertIs(dialer.active, person)
            self.assertTrue(loser["skip_closed"])
            self.assertNotIn(loser["token"], dialer.in_flight)

            kept = crm.snapshot()[1]
            self.assertEqual(kept["status"], "new")
            self.assertIsNone(kept["scheduled_until"])
            self.assertEqual([item["answered_by"] for item in kept["call_log"]], ["race_lost"])
            self.assertTrue(calls._dialed_recently(kept))
            self.assertFalse(calls._dialed_recently(kept, utc_now() + timedelta(minutes=3)))
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_an_unclear_answer_connects_unless_the_line_picked_up_instantly(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            instant = dialer._new_call("prospect", leads[0])
            instant["line_seen_at"], instant["answered_at"] = 100.0, 100.6
            dialer._machine_result(instant, {"AnsweredBy": "unknown"})
            self.assertIsNone(dialer.active)
            self.assertTrue(instant["skip_closed"])
            first = crm.snapshot()[0]
            self.assertEqual(first["status"], "new")
            self.assertEqual([item["answered_by"] for item in first["call_log"]], ["unclear"])

            ringing = dialer._new_call("prospect", leads[1])
            ringing["line_seen_at"], ringing["answered_at"] = 100.0, 111.0
            dialer._machine_result(ringing, {"AnsweredBy": "unknown"})
            self.assertIs(dialer.active, ringing)
            self.assertTrue(ringing["picked_up"])
            self.assertEqual(ringing["answered_by"], "unknown")
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_instant_answer_is_measured_from_the_first_status_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 1)
            call = dialer._new_call("prospect", crm.snapshot()[0])
            dialer.handle_webhook(call["token"], "status", {"CallStatus": "initiated"})
            dialer.handle_webhook(call["token"], "answer", {})
            self.assertIsNotNone(call["line_seen_at"])
            self.assertGreaterEqual(call["answered_at"], call["line_seen_at"])
            seen = call["line_seen_at"]
            dialer.handle_webhook(call["token"], "status", {"CallStatus": "in-progress"})
            self.assertEqual(call["line_seen_at"], seen)

    def test_retry_wait_depends_on_how_the_dial_ended(self):
        now = utc_now()

        def lead(answered_by, ago):
            return {"call_log": [{"id": "x", "started_at": (now - ago).isoformat(), "answered_by": answered_by}]}

        self.assertTrue(calls._dialed_recently(lead("no_answer", timedelta(hours=1)), now))
        self.assertFalse(calls._dialed_recently(lead("no_answer", timedelta(hours=4)), now))
        self.assertTrue(calls._dialed_recently(lead("voicemail", timedelta(hours=3)), now))
        self.assertFalse(calls._dialed_recently(lead("voicemail", timedelta(hours=5)), now))
        self.assertTrue(calls._dialed_recently(lead("race_lost", timedelta(seconds=30)), now))
        self.assertFalse(calls._dialed_recently(lead("race_lost", timedelta(minutes=3)), now))
        self.assertTrue(calls._dialed_recently(lead("unknown", timedelta(hours=5)), now))
        self.assertTrue(calls._dialed_recently(lead("", timedelta(hours=5)), now))
        self.assertFalse(calls._dialed_recently(lead("unknown", timedelta(hours=13)), now))
