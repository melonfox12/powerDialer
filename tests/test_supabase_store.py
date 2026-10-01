import base64
import io
import unittest
from unittest.mock import patch

from supabase_store import SupabaseClient


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
        response = io.BytesIO(b"[]")
        response.__enter__ = lambda: response
        response.__exit__ = lambda *args: None
        with patch("supabase_store.urllib.request.urlopen", return_value=response) as urlopen:
            client = SupabaseClient("https://project.supabase.co", "sb_secret_test")
            self.assertEqual(client.request("GET", "prospects"), [])

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Apikey"), "sb_secret_test")
        self.assertEqual(request.get_header("Authorization"), "Bearer sb_secret_test")


if __name__ == "__main__":
    unittest.main()
