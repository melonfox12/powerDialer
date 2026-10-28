import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from features.prospects import ProspectStore
from features._dialer import calls
from features._dialer.rules import new_session
from features.dialer import Dialer
from shared.infra import utc_now
from shared.vocabulary import NO_PICKUP_CALLBACK_HOURS

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
            first_after = crm.snapshot()[0]
            self.assertEqual(first_after["status"], "call")
            self.assertTrue(first_after["scheduled_until"])
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

    def test_prospect_hangup_after_live_connect_schedules_next_dial(self):
        from features._dialer import timing
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {
                "CALLING_START_HOUR": "0",
                "CALLING_END_HOUR": "24",
                "AUTO_ADVANCE_DELAY_SECONDS": "0",
            }
            call = dialer._new_call("prospect", leads[0])
            call["call_uuid"] = "CA-prospect-hangup"
            dialer._pickup(call)
            dialer._machine_result(call, {"AnsweredBy": "human"})
            self.assertIsNone(dialer.pending_outcome)
            dialer._call_ended(call, {"CallStatus": "completed", "CallDuration": "18"})
            self.assertIsNone(dialer.pending_outcome)
            self.assertIsNotNone(dialer.advance_timer)
            if dialer.advance_timer:
                dialer.advance_timer.cancel()
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            try:
                timing._advance_queue(dialer)
            finally:
                calls._launch_call = original_launch
            self.assertNotIn(leads[0]["id"], launched)
            self.assertIn(leads[1]["id"], launched)

    def test_no_answer_moves_new_prospect_to_forty_eight_hour_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            lead = crm.snapshot()[0]
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-miss"
            dialer._call_ended(call, {"CallStatus": "no-answer", "CallDuration": "0"})
            kept = crm.snapshot()[0]
            self.assertEqual(kept["status"], "call")
            self.assertTrue(kept["scheduled_until"])
            launched = []
            original_launch = calls._launch_call
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            try:
                dialer.fill_slots()
            finally:
                calls._launch_call = original_launch
                if dialer.advance_timer:
                    dialer.advance_timer.cancel()
            self.assertNotIn(lead["id"], launched)
            self.assertEqual(launched, [crm.snapshot()[1]["id"]])

    def test_parallel_no_answer_tops_up_while_a_sibling_still_rings(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 3)
            leads = crm.snapshot()
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            ringing = dialer._new_call("prospect", leads[1])
            ringing["call_uuid"] = "CA-ringing"
            missed = dialer._new_call("prospect", leads[0])
            missed["call_uuid"] = "CA-miss"
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            try:
                dialer._call_ended(missed, {"CallStatus": "no-answer", "CallDuration": "0"})
                time.sleep(0.3)
                self.assertEqual(launched, [leads[2]["id"]])
                self.assertIn(ringing["token"], dialer.in_flight)
            finally:
                calls._launch_call = original_launch
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
            kept = crm.snapshot()[0]
            self.assertEqual(kept["status"], "call")
            self.assertTrue(kept["scheduled_until"])
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

    def test_a_line_that_loses_the_race_becomes_a_forty_eight_hour_callback_logged_once(self):
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
            self.assertEqual(kept["status"], "call")
            remaining = datetime.fromisoformat(kept["scheduled_until"]) - utc_now()
            self.assertGreater(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS) - timedelta(seconds=5))
            self.assertLessEqual(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS))
            self.assertEqual([item["answered_by"] for item in kept["call_log"]], ["race_lost"])
            # Reading the state must not add a second record for the callback.
            dialer.public_state()
            self.assertEqual([item["answered_by"] for item in crm.snapshot()[1]["call_log"]], ["race_lost"])
            self.assertNotIn(kept["id"], {lead["id"] for lead in calls._pool_leads(dialer)})
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_a_dropped_callback_comes_back_after_forty_eight_hours_and_not_before(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            person = dialer._new_call("prospect", leads[0])
            dialer._new_call("prospect", leads[1])
            dialer._machine_result(person, {"AnsweredBy": "human"})
            dialer.active = None
            dialer.in_flight.clear()
            self.assertEqual([lead["id"] for lead in calls._pool_leads(dialer)], [])

            def move_back(hours):
                lead = crm.leads[1]
                lead["scheduled_until"] = (datetime.fromisoformat(lead["scheduled_until"]) - timedelta(hours=hours)).isoformat()
                for item in lead["call_log"]:
                    item["started_at"] = (datetime.fromisoformat(item["started_at"]) - timedelta(hours=hours)).isoformat()

            move_back(1)
            self.assertEqual(crm.snapshot()[1]["status"], "call")
            self.assertEqual([lead["id"] for lead in calls._pool_leads(dialer)], [])
            move_back(2)
            self.assertEqual(crm.snapshot()[1]["status"], "new")
            self.assertEqual([lead["id"] for lead in calls._pool_leads(dialer)], ["prospect-1"])
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_an_unclear_answer_still_connects_the_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 1)
            dialer.running = True
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["call_uuid"] = "CA-unclear"
            dialer.handle_webhook(call["token"], "status", {"CallStatus": "initiated"})
            dialer.handle_webhook(call["token"], "answer", {})
            dialer._machine_result(call, {"AnsweredBy": "unknown"})
            self.assertIs(dialer.active, call)
            self.assertTrue(call.get("picked_up"))
            self.assertEqual(call["answered_by"], "unknown")
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_machine_start_hangs_up_without_connecting_the_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 1)
            dialer.running = True
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["call_uuid"] = "CA-early-machine"
            dialer._machine_result(call, {"AnsweredBy": "machine_start"})
            self.assertIsNone(dialer.active)
            self.assertFalse(call.get("picked_up"))
            self.assertEqual(call["answered_by"], "voicemail")
            self.assertTrue(call.get("skip_closed"))
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_an_unclear_answer_on_a_line_that_already_hung_up_is_not_connected(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 1)
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["call_uuid"] = "CA-gone"
            with patch("features._dialer.twilio._call_is_live", return_value=False):
                dialer._machine_result(call, {"AnsweredBy": "unknown"})
            self.assertIsNone(dialer.active)
            self.assertFalse(call.get("picked_up"))
            self.assertTrue(call["skip_closed"])
            self.assertEqual([item["answered_by"] for item in crm.snapshot()[0]["call_log"]], ["dead_line"])
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_wrapped_ended_call_is_stale_and_fill_slots_can_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            finished = dialer._new_call("prospect", leads[0])
            dialer._pickup(finished)
            finished["wrapping"] = True
            finished["end_processed"] = True
            finished["state"] = "ended"
            dialer.active = finished
            dialer.in_flight.clear()
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            try:
                dialer.fill_slots()
            finally:
                calls._launch_call = original_launch
                if dialer.advance_timer:
                    dialer.advance_timer.cancel()
            self.assertIsNone(dialer.active)
            self.assertEqual(launched, [leads[1]["id"]])

    def test_disposition_after_agent_hangup_schedules_auto_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24", "AUTO_ADVANCE_DELAY_SECONDS": "3"}
            lead = crm.snapshot()[0]
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-live"
            dialer._pickup(call)
            dialer.hangup_active()
            self.assertEqual(dialer.pending_outcome, lead["id"])
            dialer._call_ended(call, {"CallStatus": "completed", "CallDuration": "40"})
            self.assertIsNone(dialer.advance_timer)
            dialer.update_status(lead["id"], "send_info")
            self.assertIsNotNone(dialer.advance_timer)
            dialer.advance_timer.cancel()

    def test_stale_active_does_not_block_the_next_pickup(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 2)
            leads = crm.snapshot()
            first = dialer._new_call("prospect", leads[0])
            first["call_uuid"] = "CA-first"
            dialer._pickup(first)
            first["end_processed"] = True
            first["state"] = "ended"
            dialer.active = first

            second = dialer._new_call("prospect", leads[1])
            second["call_uuid"] = "CA-second"
            dialer._machine_result(second, {"AnsweredBy": "human"})
            self.assertIs(dialer.active, second)
            self.assertTrue(second["picked_up"])

            _, _, twiml = dialer.handle_webhook(second["token"], "answer", {"CallSid": "CA-second"})
            self.assertIn("<Conference", twiml)
            self.assertNotIn("<Hangup", twiml)
            view = dialer.public_state()
            self.assertEqual(view["stage"], "connected")
            self.assertEqual(view["active_lead"]["id"], leads[1]["id"])
            if dialer.advance_timer:
                dialer.advance_timer.cancel()

    def test_cancel_call_clears_active_when_it_was_live(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer_with_leads(directory, 1)
            call = dialer._new_call("prospect", crm.snapshot()[0])
            dialer._pickup(call)
            calls._cancel_call(dialer, call)
            self.assertIsNone(dialer.active)
            self.assertTrue(call["cancelled"])

    def test_retry_wait_depends_on_how_the_dial_ended(self):
        now = utc_now()

        def lead(answered_by, ago):
            return {"call_log": [{"id": "x", "started_at": (now - ago).isoformat(), "answered_by": answered_by}]}

        self.assertTrue(calls._dialed_recently(lead("no_answer", timedelta(hours=1)), now))
        self.assertFalse(calls._dialed_recently(lead("no_answer", timedelta(hours=3)), now))
        self.assertTrue(calls._dialed_recently(lead("voicemail", timedelta(hours=1)), now))
        self.assertFalse(calls._dialed_recently(lead("voicemail", timedelta(hours=3)), now))
        self.assertTrue(calls._dialed_recently(lead("race_lost", timedelta(hours=1)), now))
        self.assertFalse(calls._dialed_recently(lead("race_lost", timedelta(hours=3)), now))
        self.assertTrue(calls._dialed_recently(lead("unknown", timedelta(hours=5)), now))
        self.assertTrue(calls._dialed_recently(lead("", timedelta(hours=1)), now))
        self.assertFalse(calls._dialed_recently(lead("unknown", timedelta(hours=13)), now))
