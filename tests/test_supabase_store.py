import base64
import unittest

from shared.infra import SupabaseClient


def jwt_with_role(role):
    payload = base64.urlsafe_b64encode(
        ('{"role":"' + role + '"}').encode("utf-8")
    ).decode("ascii").rstrip("=")
    return f"header.{payload}.signature"


class SupabaseClientTests(unittest.TestCase):
    def test_requires_https_project_url(self):
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            SupabaseClient("http://project.supabase.co", "sb_secret_test")

    def test_rejects_publishable_key_for_server_storage(self):
        with self.assertRaisesRegex(ValueError, "publishable/anon"):
            SupabaseClient("https://project.supabase.co", "sb_publishable_test")

    def test_rejects_non_service_role_jwt(self):
        with self.assertRaisesRegex(ValueError, "service_role"):
            SupabaseClient("https://project.supabase.co", jwt_with_role("anon"))

    def test_accepts_legacy_service_role_jwt(self):
        client = SupabaseClient("https://project.supabase.co", jwt_with_role("service_role"))
        self.assertEqual(client.base_url, "https://project.supabase.co/rest/v1/")

    def test_from_env_uses_secret_key_and_requires_both_values(self):
        self.assertIsNone(SupabaseClient.from_env({}))
        with self.assertRaisesRegex(ValueError, "Configure both"):
            SupabaseClient.from_env({"SUPABASE_URL": "https://project.supabase.co"})

        client = SupabaseClient.from_env({
            "SUPABASE_URL": "https://project.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
            "SUPABASE_SERVICE_ROLE_KEY": "sb_publishable_not-used",
        })
        self.assertEqual(client.service_key, "sb_secret_test")

    def test_rest_request_sends_server_key_headers(self):
        client = SupabaseClient("https://project.supabase.co", "sb_secret_test")
        seen = {}

        def fake_send(method, path, body, headers):
            seen["method"] = method
            seen["path"] = path
            seen["headers"] = headers
            return 200, b"[]"

        client._pool.send = fake_send
        self.assertEqual(client.request("GET", "prospects"), [])
        self.assertEqual(seen["method"], "GET")
        self.assertTrue(seen["path"].startswith("/rest/v1/prospects"))
        self.assertEqual(seen["headers"]["apikey"], "sb_secret_test")
        self.assertEqual(seen["headers"]["Authorization"], "Bearer sb_secret_test")
        self.assertEqual(client.project_url, "https://project.supabase.co")

    def test_auth_user_requires_access_token(self):
        client = SupabaseClient("https://project.supabase.co", "sb_secret_test", anon_key="anon")
        self.assertIsNone(client.auth_user(""))
        self.assertIsNone(client.auth_user(None))


class MigrationTests(unittest.TestCase):
    def test_every_written_row_belongs_to_the_given_user(self):
        import json
        import tempfile
        from pathlib import Path

        from scripts.migrate_to_supabase import migrate_local_data

        written = []

        class RecordingClient:
            def select_all(self, resource, params=None):
                return []

            def request(self, method, resource, params=None, payload=None, prefer=None):
                written.append((resource, payload))

        user_id = "11111111-1111-1111-1111-111111111111"
        with tempfile.TemporaryDirectory() as directory:
            crm_path = Path(directory) / "crm.json"
            crm_path.write_text(json.dumps([{
                "id": "prospect-1", "name": "Onyx", "phone": "+12025550123",
                "status": "new", "scheduled_until": None, "transcript": [], "fields": {},
            }]), encoding="utf-8")
            metrics_path = Path(directory) / "metrics.json"
            metrics_path.write_text(json.dumps({
                "daily": {"2026-10-01": {"dials": 3}},
                "all_time": {"dials": 3},
                "sessions": [{"id": "s1", "started_at": "2026-10-01T10:00:00+00:00"}],
            }), encoding="utf-8")
            migrate_local_data(RecordingClient(), crm_path, metrics_path, user_id)
        self.assertEqual(
            sorted(resource for resource, _rows in written),
            ["dialer_metric_daily", "dialer_metric_totals", "dialer_sessions", "prospects"],
        )
        for resource, rows in written:
            for row in rows:
                self.assertEqual(row["user_id"], user_id, resource)

    def test_user_id_argument_is_required(self):
        from scripts.migrate_to_supabase import main

        with self.assertRaises(SystemExit):
            main([])
        with self.assertRaises(SystemExit):
            main(["--user-id", "not-a-uuid"])

if __name__ == "__main__":
    unittest.main()
