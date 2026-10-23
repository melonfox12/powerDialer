import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from features import performance
from features.dialer import Dialer
from features.metrics import MetricsStore
from features.prospects import ProspectStore
from features.settings import preferences, save_goal
from shared.vocabulary import SETTING_DEFAULTS

NOW = datetime(2026, 10, 23, 16, 0, tzinfo=timezone.utc)
NEW_YORK = ZoneInfo("America/New_York")
REAL_NOW = datetime.now(timezone.utc)


def call(minutes_ago, connected=True, seconds=0, answered_by="human", outcome=None, **extra):
    started = NOW - timedelta(minutes=minutes_ago)
    entry = {
        "id": f"call-{minutes_ago}-{seconds}-{connected}",
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(seconds=seconds)).isoformat(),
        "answered_by": answered_by,
        "duration_seconds": seconds,
        "connected": connected,
        "outcome": outcome,
    }
    entry.update(extra)
    return entry


def lead(lead_id, calls=(), status="call", booked_at=None, status_history=None):
    row = {
        "id": lead_id,
        "name": lead_id,
        "business": "",
        "status": status,
        "call_log": list(calls),
        "booked_at": booked_at,
    }
    if status_history is not None:
        row["status_history"] = status_history
    return row


GOAL = {"conversation_goal": 20, "talk_minutes_goal": 60, "minutes": 60, "weekly_step": 0, "anchor": ""}


class RateTests(unittest.TestCase):
    def test_zero_denominator_is_none_not_nan(self):
        self.assertIsNone(performance.rate(0, 0))
        self.assertIsNone(performance.rate(5, 0))
        self.assertEqual(performance.rate(1, 4), 0.25)

    def test_format_funnel_percent(self):
        self.assertEqual(performance.format_funnel_percent(None), "—")
        self.assertEqual(performance.format_funnel_percent(0.5), "50%")
        self.assertEqual(performance.format_funnel_percent(0.052), "5.2%")
        self.assertEqual(performance.format_funnel_percent(0.12), "12%")


class CallRecordTests(unittest.TestCase):
    def test_race_lost_and_voicemail_are_not_connects(self):
        entries = [
            {"id": "a", "started_at": NOW.isoformat(), "answered_by": "race_lost", "duration_seconds": 0},
            {"id": "b", "started_at": NOW.isoformat(), "answered_by": "voicemail", "duration_seconds": 30},
        ]
        records = performance.call_records([lead("x", entries)])
        self.assertEqual([record["connected"] for record in records], [False, False])

    def test_conversation_needs_sixty_connected_seconds(self):
        records = performance.call_records([lead("x", [call(1, seconds=59), call(2, seconds=60), call(3, connected=False, seconds=90)])])
        self.assertEqual(sum(performance.is_conversation(record) for record in records), 1)

    def test_voicemail_is_never_a_conversation(self):
        records = performance.call_records([lead("x", [call(1, seconds=120, answered_by="voicemail")])])
        self.assertFalse(performance.is_conversation(records[0]))


class WindowTests(unittest.TestCase):
    def test_week_window_is_seven_local_days(self):
        start, end = performance.range_windows("week", NOW, NEW_YORK)
        self.assertEqual(end, NOW.astimezone(timezone.utc))
        self.assertEqual(start, datetime(2026, 10, 17, 4, 0, tzinfo=timezone.utc))

    def test_day_window_is_twenty_four_hours(self):
        start, end = performance.range_windows("day", NOW, NEW_YORK)
        self.assertEqual(end - start, timedelta(hours=24))

    def test_month_window_is_thirty_local_days(self):
        start, end = performance.range_windows("month", NOW, NEW_YORK)
        self.assertEqual(start, datetime(2026, 9, 24, 4, 0, tzinfo=timezone.utc))


class BookedHistoryTests(unittest.TestCase):
    def test_active_booking_requires_current_booked_status(self):
        history = [{"from_status": "call", "to_status": "booked", "changed_at": NOW.isoformat()}]
        booked = lead("a", status="call", status_history=history)
        self.assertIsNone(performance.active_booking_moment(booked))

    def test_backfill_uses_booked_at_and_marks_estimated(self):
        at = (NOW - timedelta(days=1)).isoformat()
        row = lead("a", status="booked", booked_at=at)
        history = performance.status_history_for(row)
        self.assertTrue(history[-1]["estimated"])
        self.assertEqual(performance.active_booking_moment(row)["at"], performance.parse_moment(at))

    def test_pipeline_booked_matches_history_when_status_booked(self):
        rows = [
            lead("a", status="booked", booked_at=NOW.isoformat()),
            lead("b", status="call"),
        ]
        self.assertEqual(performance.count_booked_in_pipeline(rows), 1)
        self.assertEqual(performance.count_booked_from_history(rows), 1)

    def test_leaving_booked_removes_from_counts(self):
        history = [
            {"from_status": "call", "to_status": "booked", "changed_at": (NOW - timedelta(days=1)).isoformat()},
            {"from_status": "booked", "to_status": "call", "changed_at": NOW.isoformat()},
        ]
        row = lead("a", status="call", status_history=history)
        self.assertIsNone(performance.active_booking_moment(row))
        self.assertEqual(performance.count_booked_from_history([row]), 0)

    def test_reentry_counts_once_at_latest_transition(self):
        history = [
            {"from_status": "call", "to_status": "booked", "changed_at": (NOW - timedelta(days=3)).isoformat()},
            {"from_status": "booked", "to_status": "call", "changed_at": (NOW - timedelta(days=2)).isoformat()},
            {"from_status": "call", "to_status": "booked", "changed_at": (NOW - timedelta(days=1)).isoformat()},
        ]
        row = lead("a", status="booked", status_history=history)
        moment = performance.active_booking_moment(row)
        self.assertEqual(moment["at"], performance.parse_moment(history[-1]["changed_at"]))


class BuildPerformanceTests(unittest.TestCase):
    def build(self, leads, range_key="week", goal=GOAL):
        return performance.build_performance(leads, [], goal, range_key, "America/New_York", NOW)

    def test_funnel_and_counts(self):
        calls = [call(10, seconds=90), call(20, seconds=30), call(30, connected=False)]
        booked = lead(
            "b",
            [],
            status="booked",
            status_history=[{"from_status": "call", "to_status": "booked", "changed_at": (NOW - timedelta(minutes=5)).isoformat()}],
        )
        result = self.build([lead("a", calls), booked])
        counts = result["counts"]
        self.assertEqual(counts["dials"], 3)
        self.assertEqual(counts["connected"], 2)
        self.assertEqual(counts["conversations"], 1)
        self.assertEqual(counts["booked"], 1)
        self.assertAlmostEqual(result["funnel"]["dials_to_connected"], 2 / 3)
        self.assertAlmostEqual(result["funnel"]["connected_to_conversations"], 0.5)
        self.assertAlmostEqual(result["funnel"]["conversations_to_booked"], 1.0)

    def test_talk_time_sums_connected_seconds_in_range(self):
        calls = [call(10, seconds=40), call(20, seconds=50)]
        counts = performance.window_counts(
            performance.call_records([lead("a", calls)]),
            [lead("a", calls)],
            {},
            NOW - timedelta(hours=1),
            NOW,
        )
        self.assertEqual(counts["talk_seconds"], 90)

    def test_talk_time_ignores_voicemail(self):
        calls = [call(10, seconds=120, answered_by="voicemail"), call(20, seconds=30)]
        counts = performance.window_counts(
            performance.call_records([lead("a", calls)]),
            [lead("a", calls)],
            {},
            NOW - timedelta(hours=1),
            NOW,
        )
        self.assertEqual(counts["talk_seconds"], 30)

    def test_daily_goals_use_local_midnight(self):
        calls = [call(10, seconds=75)]
        result = self.build([lead("a", calls)])
        self.assertEqual(result["daily"]["conversations"], 1)
        self.assertAlmostEqual(result["daily"]["talk_minutes"], 75 / 60)

    def test_week_trend_has_seven_day_buckets(self):
        result = self.build([lead("a", [call(10)])])
        self.assertEqual(result["trend"]["grain"], "day")
        self.assertEqual(len(result["trend"]["buckets"]), 7)

    def test_day_trend_is_hourly(self):
        result = self.build([lead("a", [call(10)])], range_key="day")
        self.assertEqual(result["trend"]["grain"], "hour")
        self.assertEqual(len(result["trend"]["buckets"]), 24)


class GoalSettingsTests(unittest.TestCase):
    def test_defaults_include_conversation_goal(self):
        parsed = preferences({key: "" for key in SETTING_DEFAULTS})
        self.assertEqual(parsed["DAILY_CONVERSATION_GOAL"], "20")
        self.assertEqual(parsed["DAILY_GOAL_MINUTES"], "60")

    def test_save_goal_stores_conversation_goal(self):
        with tempfile.TemporaryDirectory() as directory:
            env = str(Path(directory) / ".env")
            saved = save_goal(env, {}, None, {"daily_conversation_goal": 25, "daily_goal_minutes": 45}, date(2026, 10, 23))
            self.assertEqual(saved["DAILY_CONVERSATION_GOAL"], "25")
            self.assertEqual(saved["DAILY_GOAL_MINUTES"], "45")


class OutcomeTaggingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        self.crm = ProspectStore(root / "crm")
        self.dialer = Dialer(self.crm, str(root / ".env"), metrics=MetricsStore(root / "metrics.json"))
        self.lead = self.crm.add_lead({"name": "Pat", "phone": "+15551230000", "timezone": "Eastern"})
        self.crm.append_call_log(self.lead["id"], {"id": "tok", "started_at": NOW.isoformat(), "connected": True})

    def connect_call(self):
        self.dialer.taggable_call = {"token": "tok", "call_uuid": None, "lead_id": self.lead["id"], "picked_up": True}

    def test_booked_tag_records_status_history(self):
        self.connect_call()
        self.dialer.tag_call(self.lead["id"], "booked")
        stored = next(item for item in self.crm.snapshot() if item["id"] == self.lead["id"])
        self.assertEqual(stored["status"], "booked")
        self.assertTrue(any(item.get("to_status") == "booked" for item in stored.get("status_history") or []))
        result = performance.build_performance(self.crm.snapshot(), [], GOAL, "week", "UTC", datetime.now(timezone.utc) + timedelta(minutes=1))
        self.assertEqual(result["metrics_booked"], result["pipeline_booked"])


if __name__ == "__main__":
    unittest.main()
