import unittest
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from crm_store import CRMStore
from dialer_session import (
    add_connect,
    dialer_stage,
    local_time,
    new_session,
    record_conversation,
    record_disposition,
    recent_streak,
    session_summary,
    status_for_disposition,
    within_calling_window,
)
from metrics_store import MetricsStore
from twilio_calls import TwilioDialer, _preferences, DIALER_DEFAULTS, TokenIndex


class DialerSessionTests(unittest.TestCase):
    def test_call_tokens_route_to_the_dialer_that_created_them(self):
        index = TokenIndex()
        with tempfile.TemporaryDirectory() as directory:
            first = TwilioDialer(CRMStore(Path(directory) / "a.json"), str(Path(directory) / "a.env"))
            second = TwilioDialer(CRMStore(Path(directory) / "b.json"), str(Path(directory) / "b.env"))
            first.token_index = index
            second.token_index = index
            first_token = first._new_call("agent", None)["token"]
            second_token = second._new_call("agent", None)["token"]
            self.assertIs(index.lookup(first_token), first)
            self.assertIs(index.lookup(second_token), second)

    def test_blank_preference_values_keep_defaults(self):
        preferences = _preferences({key: "" for key in DIALER_DEFAULTS})
        self.assertEqual(preferences["SESSION_GOAL"], "20")
        self.assertEqual(preferences["CONVERSATION_THRESHOLD_SECONDS"], "30")
        self.assertEqual(preferences["SOUNDS_ENABLED"], "true")
        self.assertEqual(preferences["OPENING_SCRIPT"], "")

    def test_stage_transitions_use_explicit_state_priority(self):
        self.assertEqual(dialer_stage(False, False, None, False, []), "idle")
        self.assertEqual(dialer_stage(True, False, None, False, [{"state": "creating"}]), "dialing")
        self.assertEqual(dialer_stage(True, False, None, False, [{"state": "ringing"}]), "ringing")
        self.assertEqual(dialer_stage(True, False, object(), False, []), "connected")
        self.assertEqual(dialer_stage(True, False, None, True, []), "wrapup")
        self.assertEqual(dialer_stage(True, True, None, False, []), "paused")

    def test_disposition_mapping(self):
        expected = {
            "booked": "booked",
            "callback": "call",
            "not_interested": "disqualified",
            "no_answer": "call",
            "do_not_call": "do_not_call",
        }
        for disposition, status in expected.items():
            with self.subTest(disposition=disposition):
                self.assertEqual(status_for_disposition(disposition), status)
        with self.assertRaises(ValueError):
            status_for_disposition("unknown")

    def test_local_time_and_calling_window_respect_prospect_timezone(self):
        instant = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)
        eastern = local_time("Eastern", instant)
        self.assertEqual((eastern.hour, eastern.minute), (11, 0))
        self.assertTrue(within_calling_window("Eastern", now=instant))
        self.assertTrue(within_calling_window("Eastern", now=datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)))
        self.assertFalse(within_calling_window("Eastern", now=datetime(2026, 10, 2, 1, 0, tzinfo=timezone.utc)))
        self.assertFalse(within_calling_window("Unknown", now=instant))

    def test_session_statistics_and_conversation_threshold(self):
        session = new_session(goal=2, started_at="2026-10-01T10:00:00+00:00")
        first = datetime(2026, 10, 1, 10, 1, tzinfo=timezone.utc)
        second = datetime(2026, 10, 1, 10, 6, tzinfo=timezone.utc)
        add_connect(session, first)
        add_connect(session, second)
        self.assertEqual(recent_streak(session, second), 2)
        self.assertFalse(record_conversation(session, 29, 30))
        self.assertTrue(record_conversation(session, 30, 30))
        self.assertTrue(record_conversation(session, 45, 30))
        record_disposition(session, "interested")
        record_disposition(session, "booked")
        self.assertEqual(session["connects"], 2)
        self.assertEqual(session["conversations"], 2)
        self.assertEqual(session["meetings_booked"], 1)
        summary = session_summary(session, "2026-10-01T10:10:00+00:00")
        self.assertEqual(summary["duration_seconds"], 600)
        self.assertEqual(summary["best_streak"], 2)
        self.assertNotIn("connect_times", summary)

    def test_session_history_persists_in_local_metrics_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MetricsStore(Path(directory) / "metrics.json")
            session = new_session(goal=3, started_at="2026-10-01T10:00:00+00:00")
            session["dials"] = 4
            store.save_session(session)
            self.assertEqual(store.recent_sessions()[0]["dials"], 4)

    def test_call_flow_settings_persist_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            crm = CRMStore(Path(directory) / "crm.json")
            dialer = TwilioDialer(crm, str(env_path))
            settings = dialer.save_settings({
                "session_goal": "25",
                "conversation_threshold": "45",
                "auto_advance_delay": "4",
                "sounds_enabled": False,
                "sound_volume": "20",
                "break_nudge_minutes": "60",
                "calling_start_hour": "9",
                "calling_end_hour": "20",
                "opening_script": "Confirm the owner.\nAsk a clear question.",
            })
            self.assertEqual(settings["session_goal"], 25)
            self.assertEqual(settings["conversation_threshold"], 45)
            self.assertEqual(settings["opening_script"], "Confirm the owner.\nAsk a clear question.")
            persisted = dialer.settings_state()
            self.assertFalse(persisted["sounds_enabled"])
            self.assertEqual(persisted["calling_start_hour"], 9)
            with self.assertRaisesRegex(ValueError, "end must be later"):
                dialer.save_settings({
                    "session_goal": "20",
                    "calling_start_hour": "20",
                    "calling_end_hour": "20",
                })

    def test_signed_in_settings_are_saved_to_the_account(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            crm = CRMStore(Path(directory) / "crm.json")
            dialer = TwilioDialer(crm, str(env_path))
            dialer.account_user_id = "user-1"
            saved = []
            dialer.settings_saver = saved.append
            dialer.save_settings({
                "account_sid": "ACexample",
                "auth_token": "token",
                "api_key": "SKexample",
                "api_secret": "secret",
                "twiml_app_sid": "APexample",
                "public_base_url": "https://example.ngrok.dev",
                "session_goal": "12",
            })
            self.assertEqual(saved[0].account_values["TWILIO_ACCOUNT_SID"], "ACexample")
            self.assertEqual(saved[0].account_values["PUBLIC_BASE_URL"], "https://example.ngrok.dev")
            self.assertEqual(saved[0].account_values["SESSION_GOAL"], "12")
            self.assertNotIn("ACexample", env_path.read_text(encoding="utf-8") if env_path.exists() else "")

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

    def test_answer_bridges_any_pickup_and_keeps_voicemail_on_the_line(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.public_base_url = "https://example.test"
            dialer.conference = "crm-test"
            dialer.save_settings({"session_goal": 20})
            dialer.running = True
            dialer.session = new_session()
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-test"
            call["caller_id"] = "+15551230001"

            status, _, twiml = dialer.handle_webhook(call["token"], "answer", {"CallSid": "CA-test"})
            self.assertEqual(status, 200)
            self.assertIn("<Transcription", twiml)
            self.assertIn("<Conference", twiml)
            self.assertNotIn("<Pause", twiml)
            self.assertNotIn("Please hold", twiml)
            self.assertEqual(call["state"], "live")
            self.assertIs(dialer.active, call)
            self.assertEqual(dialer.public_state()["live_transcript"]["lead_id"], lead["id"])
            self.assertEqual(dialer.public_state()["current_caller_id"], "+15551230001")

            hung = []
            dialer._hangup_call = lambda call_uuid: hung.append(call_uuid)
            dialer._machine_result(call, {"AnsweredBy": "machine_end_beep"})
            self.assertEqual(hung, [])
            self.assertEqual(call["answered_by"], "voicemail")
            self.assertIs(dialer.active, call)
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            self.assertEqual(dialer.session["connects"], 1)

    def test_rep_can_manually_enter_listening_line(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.public_base_url = "https://example.test"
            dialer.save_settings({"session_goal": 20})
            dialer.running = True
            dialer.agent_ready = True
            call = dialer._new_call("prospect", lead)
            call.update({"call_uuid": "CA-test", "state": "listening"})
            transferred = []
            dialer._transfer = lambda call_uuid, url: transferred.append(call_uuid)

            result = dialer.enter_live_line()

            self.assertIs(dialer.active, call)
            self.assertEqual(result["active_lead"]["id"], lead["id"])
            self.assertEqual(transferred, ["CA-test"])

    def test_slow_answer_detection_does_not_drop_the_line(self):
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
            call = dialer._new_call("prospect", lead)
            call.update({"call_uuid": "CA-test", "state": "live", "picked_up": True})
            dialer.active = call

            dialer._answer_detection_timeout(call)

            self.assertIn(call["token"], dialer.in_flight)
            self.assertIs(dialer.active, call)
            self.assertEqual(crm.snapshot()[0]["status"], "new")

    def test_caller_ids_rotate_and_only_one_prospect_is_dialed(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            leads = []
            for index in range(4):
                leads.append({
                    "id": f"prospect-{index}",
                    "name": f"Prospect {index}",
                    "business": "Shop",
                    "phone": f"+1202555012{index}",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                })
            crm.leads = leads
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            dialer._launch_call = lambda call, destination: launched.append((call["caller_id"], destination))

            dialer.fill_slots()
            dialer.fill_slots()
            self.assertEqual(len(launched), 1)
            self.assertEqual(launched[0][0], "+15551110001")

            dialer.in_flight.clear()
            dialer.active = None
            dialer.fill_slots()
            dialer.in_flight.clear()
            dialer.fill_slots()
            dialer.in_flight.clear()
            dialer.fill_slots()
            self.assertEqual(
                [caller for caller, _destination in launched],
                ["+15551110001", "+15551110002", "+15551110003", "+15551110001"],
            )


if __name__ == "__main__":
    unittest.main()
