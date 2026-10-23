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


def lead(lead_id, calls=(), status="call", booked_at=None):
    return {"id": lead_id, "name": lead_id, "business": "", "status": status, "call_log": list(calls), "booked_at": booked_at}


GOAL = {"minutes": 60, "weekly_step": 0, "anchor": ""}


class RateTests(unittest.TestCase):
    def test_zero_denominator_is_none_not_nan(self):
        self.assertIsNone(performance.rate(0, 0))
        self.assertIsNone(performance.rate(5, 0))
        self.assertEqual(performance.rate(1, 4), 0.25)

    def test_percent_change(self):
        self.assertAlmostEqual(performance.percent_change(15, 10), 0.5)
        self.assertAlmostEqual(performance.percent_change(5, 10), -0.5)
        self.assertIsNone(performance.percent_change(5, 0))
        self.assertIsNone(performance.percent_change(None, 10))

    def test_derived_metrics_with_no_data_has_no_rates(self):
        counts = performance.window_counts([], [], None, NOW)
        derived = performance.derived_metrics(counts)
        self.assertEqual(counts["dials"], 0)
        for key in ("connect_rate", "conversation_rate", "booking_rate", "avg_talk_seconds", "dials_per_meeting"):
            self.assertIsNone(derived[key])


class CallRecordTests(unittest.TestCase):
    def test_legacy_entries_without_connected_fall_back_to_answered_by(self):
        entries = [
            {"id": "a", "started_at": NOW.isoformat(), "answered_by": "human", "duration_seconds": 40},
            {"id": "b", "started_at": NOW.isoformat(), "answered_by": "no_answer", "duration_seconds": 0},
            {"id": "c", "started_at": NOW.isoformat(), "answered_by": "voicemail", "duration_seconds": 20, "connected": False},
        ]
        records = performance.call_records([lead("x", entries)])
        self.assertEqual([record["connected"] for record in records], [True, False, False])
        self.assertTrue(all(record["outcome"] is None for record in records))

    def test_skipped_entries_and_entries_without_a_time_are_not_dials(self):
        entries = [
            {"id": "a", "started_at": NOW.isoformat(), "answered_by": "skipped"},
            {"id": "b", "started_at": "", "ended_at": ""},
        ]
        self.assertEqual(performance.call_records([lead("x", entries)]), [])

    def test_conversation_needs_sixty_connected_seconds(self):
        records = performance.call_records([lead("x", [call(1, seconds=59), call(2, seconds=60), call(3, connected=False, seconds=90)])])
        self.assertEqual(sum(performance.is_conversation(record) for record in records), 1)

    def test_voicemail_is_never_a_conversation(self):
        records = performance.call_records([lead("x", [call(1, seconds=120, answered_by="voicemail")])])
        self.assertFalse(performance.is_conversation(records[0]))


class WindowTests(unittest.TestCase):
    def test_seven_day_window_compares_with_the_seven_days_before(self):
        start, end, previous_start, previous_end = performance.range_windows("7d", NOW, NEW_YORK)
        self.assertEqual(end, NOW)
        self.assertEqual(previous_end - previous_start, end - start)
        self.assertEqual(start - previous_start, timedelta(days=7))
        self.assertEqual(previous_end, previous_start + (end - start))

    def test_today_compares_with_the_same_hours_yesterday(self):
        start, end, previous_start, previous_end = performance.range_windows("today", NOW, NEW_YORK)
        self.assertEqual(start, datetime(2026, 10, 23, 4, 0, tzinfo=timezone.utc))
        self.assertEqual(previous_start, start - timedelta(days=1))
        self.assertEqual(previous_end, end - timedelta(days=1))

    def test_all_time_has_no_previous_window(self):
        start, _end, previous_start, previous_end = performance.range_windows("all", NOW, NEW_YORK)
        self.assertIsNone(start)
        self.assertIsNone(previous_start)
        self.assertIsNone(previous_end)

    def test_unknown_range_is_refused(self):
        with self.assertRaises(ValueError):
            performance.range_windows("year", NOW, NEW_YORK)

    def test_today_window_is_safe_across_a_daylight_saving_change(self):
        after_change = datetime(2026, 11, 1, 18, 0, tzinfo=timezone.utc)
        start, _end, previous_start, previous_end = performance.range_windows("today", after_change, NEW_YORK)
        self.assertEqual(start, datetime(2026, 11, 1, 4, 0, tzinfo=timezone.utc))
        self.assertEqual(previous_start, datetime(2026, 10, 31, 4, 0, tzinfo=timezone.utc))
        self.assertGreater(previous_end, previous_start)


class BuildPerformanceTests(unittest.TestCase):
    def build(self, leads, range_key="7d", sessions=(), goal=GOAL):
        return performance.build_performance(leads, list(sessions), goal, range_key, "America/New_York", NOW)

    def test_funnel_counts_and_rates(self):
        calls = [
            call(10, seconds=90, outcome="booked"), call(20, seconds=30), call(30, connected=False), call(40, connected=False),
        ]
        result = self.build([lead("a", calls, status="booked", booked_at=(NOW - timedelta(minutes=5)).isoformat())])
        metrics = result["metrics"]
        self.assertEqual(metrics["dials"]["value"], 4)
        self.assertEqual(metrics["connected"]["value"], 2)
        self.assertEqual(metrics["conversations"]["value"], 1)
        self.assertEqual(metrics["booked"]["value"], 1)
        self.assertAlmostEqual(metrics["connect_rate"]["value"], 0.5)
        self.assertAlmostEqual(metrics["conversation_rate"]["value"], 0.5)
        self.assertAlmostEqual(metrics["avg_talk_seconds"]["value"], 60)
        self.assertEqual(metrics["dials_per_meeting"]["value"], 4)

    def test_dials_per_meeting_is_none_without_bookings(self):
        result = self.build([lead("a", [call(10), call(20)])])
        self.assertIsNone(result["metrics"]["dials_per_meeting"]["value"])
        self.assertIsNone(result["metrics"]["minutes_per_meeting"]["value"])

    def test_minutes_per_meeting_uses_dialing_session_time(self):
        started = NOW - timedelta(hours=2)
        sessions = [{"id": "s", "started_at": started.isoformat(), "ended_at": (started + timedelta(minutes=60)).isoformat(), "dials": 5}]
        booked = lead("a", [call(100)], status="booked", booked_at=(NOW - timedelta(minutes=90)).isoformat())
        self.assertAlmostEqual(self.build([booked], sessions=sessions)["metrics"]["minutes_per_meeting"]["value"], 60)

    def test_change_against_the_previous_period(self):
        week = 7 * 24 * 60
        calls = [call(10), call(20), call(30), call(week + 10), call(week + 20)]
        result = self.build([lead("a", calls)])
        self.assertAlmostEqual(result["metrics"]["dials"]["change"], 0.5)

    def test_change_is_hidden_when_the_previous_period_has_no_dials(self):
        result = self.build([lead("a", [call(10), call(20)])])
        self.assertIsNone(result["metrics"]["dials"]["change"])

    def test_all_time_never_has_a_change(self):
        week = 7 * 24 * 60
        result = self.build([lead("a", [call(10), call(week + 10)])], range_key="all")
        self.assertEqual(result["metrics"]["dials"]["value"], 2)
        self.assertIsNone(result["metrics"]["dials"]["change"])

    def test_booked_without_a_date_is_listed_and_not_counted(self):
        result = self.build([lead("a", [call(10)], status="booked", booked_at=None)], range_key="all")
        self.assertEqual(result["metrics"]["booked"]["value"], 0)
        self.assertEqual(result["bookings"]["undated_count"], 1)
        self.assertEqual(result["bookings"]["undated"][0]["id"], "a")

    def test_outcome_breakdown_counts_tagged_connected_calls_only(self):
        calls = [
            call(10, outcome="gatekeeper"), call(20, outcome="gatekeeper"), call(30, outcome="call_back"),
            call(40), call(50, connected=False, outcome="gatekeeper"),
        ]
        outcomes = self.build([lead("a", calls)])["outcomes"]
        self.assertEqual(outcomes["tagged"], 3)
        shares = {item["key"]: item["share"] for item in outcomes["items"]}
        self.assertAlmostEqual(shares["gatekeeper"], 2 / 3)
        self.assertNotIn("booked", shares)

    def test_no_dials_gives_empty_state_flags(self):
        result = self.build([])
        self.assertFalse(result["has_dials"])
        self.assertEqual(result["trend"]["buckets"][0]["rate"], None)
        self.assertEqual(result["outcomes"]["items"], [])


class TrendTests(unittest.TestCase):
    def test_seven_day_trend_has_a_bucket_per_day_with_its_own_rate(self):
        calls = [call(10), call(20, connected=False), call(60 * 24 + 10), call(60 * 24 + 20), call(60 * 24 + 30, connected=False)]
        booked = lead("b", [], status="booked", booked_at=(NOW - timedelta(minutes=5)).isoformat())
        result = performance.build_performance([lead("a", calls), booked], [], GOAL, "7d", "America/New_York", NOW)
        buckets = result["trend"]["buckets"]
        self.assertEqual(result["trend"]["grain"], "day")
        self.assertEqual(len(buckets), 7)
        self.assertEqual(buckets[-1]["dials"], 2)
        self.assertAlmostEqual(buckets[-1]["rate"], 0.5)
        self.assertEqual(buckets[-1]["booked"], 1)
        self.assertAlmostEqual(buckets[-2]["rate"], 2 / 3)
        self.assertIsNone(buckets[0]["rate"])

    def test_today_trend_is_hourly(self):
        result = performance.build_performance([lead("a", [call(10)])], [], GOAL, "today", "America/New_York", NOW)
        self.assertEqual(result["trend"]["grain"], "hour")
        self.assertEqual(result["trend"]["buckets"][-1]["hour"], 12)

    def test_all_time_trend_switches_to_weeks_for_long_histories(self):
        calls = [call(10), call(60 * 24 * 200)]
        result = performance.build_performance([lead("a", calls)], [], GOAL, "all", "America/New_York", NOW)
        self.assertEqual(result["trend"]["grain"], "week")


class HeatmapTests(unittest.TestCase):
    def test_hidden_until_enough_dials(self):
        calls = [call(minute) for minute in range(1, 100)]
        heat = performance.build_performance([lead("a", calls)], [], GOAL, "7d", "America/New_York", NOW)["heatmap"]
        self.assertFalse(heat["unlocked"])
        self.assertEqual(heat["cells"], [])
        self.assertEqual(heat["total_dials"], 99)

    def test_buckets_by_local_weekday_and_hour(self):
        # 2026-10-23 is a Friday; 16:00 UTC is 12:00 in New York.
        calls = [call(1 + index, connected=index < 3) for index in range(10)]
        calls += [call(60 * 24 * 3 + index) for index in range(90)]
        heat = performance.heatmap(performance.call_records([lead("a", calls)]), None, NOW, NEW_YORK)
        self.assertTrue(heat["unlocked"])
        friday_noon = next(cell for cell in heat["cells"] if cell["weekday"] == 4 and cell["hour"] == 11)
        self.assertEqual(friday_noon["dials"], 10)
        self.assertEqual(friday_noon["connects"], 3)
        self.assertAlmostEqual(friday_noon["rate"], 0.3)
        self.assertTrue(friday_noon["qualified"])

    def test_cells_under_ten_dials_are_not_qualified(self):
        calls = [call(1 + index) for index in range(9)] + [call(60 * 24 * 3 + index) for index in range(91)]
        heat = performance.heatmap(performance.call_records([lead("a", calls)]), None, NOW, NEW_YORK)
        small = [cell for cell in heat["cells"] if cell["dials"] == 9]
        self.assertEqual(len(small), 1)
        self.assertFalse(small[0]["qualified"])


class StreakTests(unittest.TestCase):
    TODAY = date(2026, 10, 23)

    def days(self, *offsets):
        return {self.TODAY - timedelta(days=offset) for offset in offsets}

    def test_no_activity(self):
        self.assertEqual(performance.streak(set(), self.TODAY), {"current": 0, "best": 0, "active_today": False})

    def test_run_through_today(self):
        result = performance.streak(self.days(0, 1, 2, 4), self.TODAY)
        self.assertEqual(result["current"], 3)
        self.assertTrue(result["active_today"])

    def test_streak_survives_until_the_first_dial_of_today(self):
        result = performance.streak(self.days(1, 2), self.TODAY)
        self.assertEqual(result["current"], 2)
        self.assertFalse(result["active_today"])

    def test_streak_breaks_after_a_missed_day(self):
        result = performance.streak(self.days(2, 3, 4, 5), self.TODAY)
        self.assertEqual(result["current"], 0)
        self.assertEqual(result["best"], 4)

    def test_activity_days_use_the_local_date(self):
        late = NOW.replace(hour=2, minute=30)  # 22:30 the evening before in New York
        records = performance.call_records([lead("a", [{"id": "x", "started_at": late.isoformat(), "connected": True}])])
        self.assertEqual(performance.activity_days(records, [], NEW_YORK), {date(2026, 10, 22)})

    def test_sessions_that_dialed_count_as_activity(self):
        sessions = [{"started_at": NOW.isoformat(), "dials": 3}, {"started_at": (NOW - timedelta(days=1)).isoformat(), "dials": 0}]
        self.assertEqual(performance.activity_days([], sessions, NEW_YORK), {date(2026, 10, 23)})


class GoalTests(unittest.TestCase):
    def test_target_without_a_step_stays_flat(self):
        self.assertEqual(performance.daily_target(60, 0, date(2026, 10, 1), date(2026, 10, 23)), 60)

    def test_target_grows_each_full_week_and_is_capped(self):
        anchor = date(2026, 10, 1)
        self.assertEqual(performance.daily_target(60, 5, anchor, date(2026, 10, 7)), 60)
        self.assertEqual(performance.daily_target(60, 5, anchor, date(2026, 10, 8)), 65)
        self.assertEqual(performance.daily_target(60, 5, anchor, date(2026, 10, 23)), 75)
        self.assertEqual(performance.daily_target(700, 100, anchor, date(2027, 10, 1)), 720)

    def test_progress_counts_todays_session_minutes(self):
        started = NOW - timedelta(minutes=30)
        sessions = [{"id": "s", "started_at": started.isoformat(), "ended_at": None, "dials": 2}]
        result = performance.build_performance([], sessions, GOAL, "7d", "America/New_York", NOW, live_session_id="s")
        self.assertAlmostEqual(result["goal"]["minutes_today"], 30)
        self.assertEqual(result["goal"]["target_minutes"], 60)
        self.assertFalse(result["goal"]["reached"])

    def test_a_cut_off_session_without_an_end_is_not_counted(self):
        sessions = [{"id": "s", "started_at": (NOW - timedelta(minutes=30)).isoformat(), "ended_at": None, "dials": 2}]
        result = performance.build_performance([], sessions, GOAL, "7d", "America/New_York", NOW)
        self.assertEqual(result["goal"]["minutes_today"], 0)


class GoalSettingsTests(unittest.TestCase):
    def test_defaults_are_a_flat_hour(self):
        parsed = preferences({key: "" for key in SETTING_DEFAULTS})
        self.assertEqual(parsed["DAILY_GOAL_MINUTES"], "60")
        self.assertEqual(parsed["DAILY_GOAL_WEEKLY_STEP_MINUTES"], "0")

    def test_invalid_goal_is_refused(self):
        with self.assertRaises(ValueError):
            preferences({"DAILY_GOAL_MINUTES": "0"})
        with self.assertRaises(ValueError):
            preferences({"DAILY_GOAL_MINUTES": "abc"})
        with self.assertRaises(ValueError):
            preferences({"DAILY_GOAL_ANCHOR": "yesterday"})

    def test_save_goal_keeps_other_settings_and_anchors_a_weekly_step(self):
        with tempfile.TemporaryDirectory() as directory:
            env = str(Path(directory) / ".env")
            Path(env).write_text("SESSION_GOAL=33\n", encoding="utf-8")
            saved = save_goal(env, {}, None, {"daily_goal_minutes": 90, "daily_goal_weekly_step": 5}, date(2026, 10, 23))
            self.assertEqual(saved["DAILY_GOAL_MINUTES"], "90")
            self.assertEqual(saved["DAILY_GOAL_ANCHOR"], "2026-10-23")
            self.assertEqual(saved["SESSION_GOAL"], "33")
            later = save_goal(env, {}, None, {"daily_goal_minutes": 90, "daily_goal_weekly_step": 5}, date(2026, 11, 20))
            self.assertEqual(later["DAILY_GOAL_ANCHOR"], "2026-10-23")
            off = save_goal(env, {}, None, {"daily_goal_weekly_step": 0}, date(2026, 11, 20))
            self.assertEqual(off["DAILY_GOAL_ANCHOR"], "")


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

    def logged_outcome(self):
        stored = next(item for item in self.crm.snapshot() if item["id"] == self.lead["id"])
        return stored["call_log"][0]["outcome"]

    def test_tag_is_saved_on_the_call_record(self):
        self.connect_call()
        self.dialer.tag_call(self.lead["id"], "gatekeeper")
        self.assertEqual(self.logged_outcome(), "gatekeeper")
        self.dialer.tag_call(self.lead["id"], "call_back")
        self.assertEqual(self.logged_outcome(), "call_back")

    def test_tag_is_refused_without_a_connected_call_or_for_another_prospect(self):
        with self.assertRaises(ValueError):
            self.dialer.tag_call(self.lead["id"], "gatekeeper")
        self.connect_call()
        with self.assertRaises(ValueError):
            self.dialer.tag_call("someone-else", "gatekeeper")
        with self.assertRaises(ValueError):
            self.dialer.tag_call(self.lead["id"], "made_up")

    def test_booked_tag_marks_the_prospect_booked_and_dates_it(self):
        self.connect_call()
        self.dialer.tag_call(self.lead["id"], "booked")
        stored = next(item for item in self.crm.snapshot() if item["id"] == self.lead["id"])
        self.assertEqual(stored["status"], "booked")
        self.assertTrue(stored["booked_at"])
        self.assertEqual(self.logged_outcome(), "booked")
        with self.assertRaises(ValueError):
            self.dialer.tag_call(self.lead["id"], "gatekeeper")
        result = performance.build_performance(self.crm.snapshot(), [], GOAL, "all", "UTC", datetime.now(timezone.utc) + timedelta(minutes=1))
        self.assertEqual(result["metrics"]["booked"]["value"], 1)

    def test_a_tag_put_on_the_dial_time_entry_survives_the_finished_entry(self):
        self.connect_call()
        self.dialer.tag_call(self.lead["id"], "send_info")
        self.crm.append_call_log(self.lead["id"], {"id": "sid", "started_at": NOW.isoformat(), "connected": True}, replace_id="tok")
        self.assertEqual(self.logged_outcome(), "send_info")

    def test_log_booking_dates_the_meeting_and_counts_it_once(self):
        when = (REAL_NOW - timedelta(days=2)).isoformat()
        lead_record = self.dialer.log_booking(self.lead["id"], when)
        self.assertEqual(lead_record["status"], "booked")
        self.assertEqual(lead_record["booked_at"], (REAL_NOW - timedelta(days=2)).astimezone(timezone.utc).isoformat())
        with self.assertRaises(ValueError):
            self.dialer.log_booking(self.lead["id"], when)

    def test_log_booking_dates_an_undated_booked_prospect(self):
        stored = self.crm.leads
        stored[0]["status"] = "booked"
        stored[0].pop("booked_at", None)
        self.crm.save()
        lead_record = self.dialer.log_booking(self.lead["id"], (REAL_NOW - timedelta(days=9)).isoformat())
        self.assertTrue(lead_record["booked_at"].startswith((REAL_NOW - timedelta(days=9)).date().isoformat()))

    def test_log_booking_refuses_bad_dates(self):
        for bad in ("not a date", "2026-10-01T10:00:00", (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()):
            with self.assertRaises(ValueError):
                self.dialer.log_booking(self.lead["id"], bad)
        with self.assertRaises(KeyError):
            self.dialer.log_booking("missing", REAL_NOW.isoformat())


if __name__ == "__main__":
    unittest.main()
