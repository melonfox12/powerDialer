import tempfile
from datetime import datetime, timezone
from pathlib import Path
from crm_store import CRMStore
from core.dialer_session import add_connect, dialer_stage, local_time, new_session, record_conversation, record_disposition, recent_streak, session_summary, status_for_disposition, within_calling_window
from core.metrics_store import MetricsStore
from twilio_calls import TwilioDialer, TokenIndex

class Part1:
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
