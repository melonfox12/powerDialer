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
from twilio_calls import TwilioDialer


class DialerSessionTests(unittest.TestCase):
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

    def test_only_human_answers_count_as_connects_and_long_calls_as_conversations(self):
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
            unknown = dialer._new_call("prospect", lead)
            dialer._machine_result(unknown, {"AnsweredBy": "unknown"})
            self.assertEqual(dialer.session["connects"], 0)

            lead = crm.snapshot()[0]
            lead["status"] = "new"
            crm.leads[0]["status"] = "new"
            human = dialer._new_call("prospect", lead)
            dialer._machine_result(human, {"AnsweredBy": "human"})
            self.assertEqual(dialer.session["connects"], 1)
            dialer._call_ended(human, {"CallDuration": "30"})
            self.assertEqual(dialer.session["conversations"], 1)
            self.assertEqual(dialer.session["goal"], 1)


if __name__ == "__main__":
    unittest.main()
