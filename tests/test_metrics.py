import tempfile
import unittest
from pathlib import Path

from features._dialer.session_stats import new_session
from features.metrics import MetricsStore, SupabaseMetricsStore
from shared.infra import utc_now


class RecordingClient:
    def __init__(self):
        self.calls = []

    def request(self, method, resource, params=None, payload=None, prefer=None):
        self.calls.append((method, resource, params, payload))
        return None


class MetricsTests(unittest.TestCase):
    def test_session_history_persists_in_local_metrics_store(self):
        with tempfile.TemporaryDirectory() as directory:
            store = MetricsStore(Path(directory) / "metrics.json")
            session = new_session(goal=3, started_at="2026-10-01T10:00:00+00:00")
            session["dials"] = 4
            store.save_session(session)
            self.assertEqual(store.recent_sessions()[0]["dials"], 4)

    def test_supabase_bump_is_one_atomic_rpc(self):
        client = RecordingClient()
        store = SupabaseMetricsStore(client, user_id="11111111-1111-1111-1111-111111111111")
        store.bump("dials")
        store.bump("talk_seconds", 42)
        today = utc_now().date().isoformat()
        self.assertEqual(client.calls, [
            ("POST", "rpc/increment_metric", None, {
                "p_user_id": "11111111-1111-1111-1111-111111111111",
                "p_day": today,
                "p_metric_key": "dials",
                "p_amount": 1,
            }),
            ("POST", "rpc/increment_metric", None, {
                "p_user_id": "11111111-1111-1111-1111-111111111111",
                "p_day": today,
                "p_metric_key": "talk_seconds",
                "p_amount": 42,
            }),
        ])

    def test_schema_defines_increment_metric_for_service_role_only(self):
        text = (Path(__file__).resolve().parent.parent / "docs" / "supabase" / "schema.sql").read_text(encoding="utf-8")
        signature = "public.increment_metric(uuid, date, text, bigint)"
        self.assertIn("create or replace function public.increment_metric(p_user_id uuid, p_day date, p_metric_key text, p_amount bigint)", text)
        self.assertIn(f"revoke all on function {signature} from public, anon, authenticated;", text)
        self.assertIn(f"grant execute on function {signature} to service_role;", text)
