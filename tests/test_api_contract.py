import tempfile
import unittest
from pathlib import Path

from features.dialer import Dialer
from features.prospects import ProspectStore
from shared.api_contract import (
    ACTIVITY_LOG_ENTRY_KEYS,
    COUNTS_KEYS,
    DIALER_SETTINGS_KEYS,
    DIALER_STATE_KEYS,
    IN_FLIGHT_KEYS,
    LEAD_KEYS,
    LIVE_STATE_KEYS,
    LIVE_TRANSCRIPT_KEYS,
    SESSION_STATS_KEYS,
    assert_top_level_keys,
)


class ApiContractTests(unittest.TestCase):
    def test_key_tuples_are_unique(self):
        for name, keys in (
            ("DIALER_STATE_KEYS", DIALER_STATE_KEYS),
            ("LIVE_STATE_KEYS", LIVE_STATE_KEYS),
        ):
            self.assertEqual(len(keys), len(set(keys)), name)

    def test_live_state_is_state_without_pool(self):
        self.assertEqual(
            LIVE_STATE_KEYS,
            tuple(key for key in DIALER_STATE_KEYS if key != "pool"),
        )

    def test_empty_dialer_public_state_matches_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            payload = dialer.public_state(include_leads=False)
            assert_top_level_keys(payload, DIALER_STATE_KEYS)
            assert_top_level_keys(payload["settings"], DIALER_SETTINGS_KEYS)
            assert_top_level_keys(payload["counts"], COUNTS_KEYS)
            assert_top_level_keys(payload["live_transcript"], LIVE_TRANSCRIPT_KEYS)
            assert_top_level_keys(payload["session_stats"], SESSION_STATS_KEYS)
            self.assertEqual(payload["in_flight"], [])

    def test_lead_from_api_has_required_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.add_lead({
                "name": "Ada",
                "business": "Shop",
                "phone": "+12025550123",
                "timezone": "Eastern",
            })
            lead = crm.snapshot()[0]
            for key in LEAD_KEYS:
                self.assertIn(key, lead)

    def test_activity_log_entry_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            dialer = Dialer(ProspectStore(Path(directory) / "crm.json"), str(Path(directory) / ".env"))
            dialer.record_activity("hello", "web")
            entry = dialer.public_state()["activity_log"][0]
            assert_top_level_keys(entry, ACTIVITY_LOG_ENTRY_KEYS)

    def test_session_stats_omits_connect_times(self):
        with tempfile.TemporaryDirectory() as directory:
            dialer = Dialer(ProspectStore(Path(directory) / "crm.json"), str(Path(directory) / ".env"))
            dialer.session = {
                "id": "s1",
                "started_at": "2026-01-01T00:00:00+00:00",
                "ended_at": None,
                "goal": 5,
                "goal_reached_at": None,
                "dials": 1,
                "connects": 0,
                "conversations": 0,
                "meetings_booked": 0,
                "current_streak": 0,
                "best_streak": 0,
                "connect_times": [
                    "2026-01-01T00:00:00+00:00",
                    "2026-01-01T00:01:00+00:00",
                ],
            }
            stats = dialer.public_state()["session_stats"]
            assert_top_level_keys(stats, SESSION_STATS_KEYS)
            self.assertNotIn("connect_times", stats)

    def test_in_flight_row_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.add_lead({
                "name": "Ada",
                "business": "Shop",
                "phone": "+12025550123",
                "timezone": "Eastern",
            })
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["state"] = "ringing"
            row = dialer.public_state()["in_flight"][0]
            assert_top_level_keys(row, IN_FLIGHT_KEYS)
