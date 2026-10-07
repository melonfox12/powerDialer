import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from features.prospects import ProspectStore
from features.settings import load_app_settings, preferences, save_app_settings
from shared.vocabulary import SETTING_DEFAULTS
from features.dialer import Dialer


class SettingsTests(unittest.TestCase):
    def test_blank_preference_values_keep_defaults(self):
        parsed = preferences({key: "" for key in SETTING_DEFAULTS})
        self.assertEqual(parsed["SESSION_GOAL"], "20")
        self.assertEqual(parsed["CONVERSATION_THRESHOLD_SECONDS"], "30")
        self.assertEqual(parsed["SOUNDS_ENABLED"], "true")
        self.assertEqual(parsed["OPENING_SCRIPT"], "")

    def test_call_flow_settings_persist_and_validate(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            crm = ProspectStore(Path(directory) / "crm.json")
            dialer = Dialer(crm, str(env_path))
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
            crm = ProspectStore(Path(directory) / "crm.json")
            dialer = Dialer(crm, str(env_path))
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
            shown = dialer.settings_state()
            self.assertEqual(shown["auth_token"], "")
            self.assertEqual(shown["api_secret"], "")
            self.assertTrue(shown["has_auth_token"])
            self.assertTrue(shown["has_api_secret"])
            dialer.save_settings({
                "account_sid": "ACexample",
                "auth_token": "",
                "api_key": "SKexample",
                "api_secret": "",
                "twiml_app_sid": "APexample",
                "public_base_url": "https://example.ngrok.dev",
            })
            self.assertEqual(dialer.account_values["TWILIO_AUTH_TOKEN"], "token")
            self.assertEqual(dialer.account_values["TWILIO_API_SECRET"], "secret")
            dialer.save_settings({"auth_token": "replaced-token", "api_secret": "replaced-secret", "account_sid": "ACexample", "api_key": "SKexample", "twiml_app_sid": "APexample", "public_base_url": "https://example.ngrok.dev"})
            self.assertEqual(dialer.account_values["TWILIO_AUTH_TOKEN"], "replaced-token")
            self.assertEqual(dialer.account_values["TWILIO_API_SECRET"], "replaced-secret")
            self.assertNotIn("ACexample", env_path.read_text(encoding="utf-8") if env_path.exists() else "")

    def test_settings_round_trip_uses_dialer_settings_table(self):
        stored = {}

        class SettingsClient:
            def request(self, method, resource, params=None, payload=None, prefer=None):
                if resource != "dialer_settings":
                    raise AssertionError(resource)
                if method == "POST":
                    stored["row"] = payload[0] if isinstance(payload, list) else payload
                    return []
                return [stored["row"]] if stored else []

        client = SettingsClient()
        save_app_settings(client, {"SESSION_GOAL": "40", "TWILIO_ACCOUNT_SID": "ACtest"})
        loaded = load_app_settings(client)
        self.assertEqual(loaded["SESSION_GOAL"], "40")
        self.assertEqual(loaded["TWILIO_ACCOUNT_SID"], "ACtest")
        self.assertEqual(stored["row"]["id"], "app")

    def test_posted_settings_are_upserted_once(self):
        from features.accounts import AppRuntime
        from web import FeatureContext

        calls = []

        class RecordingClient:
            anon_key = "anon"

            def request(self, method, resource, params=None, payload=None, prefer=None):
                calls.append((method, resource))
                return [] if method == "GET" else None

        runtime = AppRuntime()
        runtime.client = RecordingClient()
        account = runtime.session_for({"id": "user-1", "email": "rep@example.com"})
        context = FeatureContext(SimpleNamespace(account=account, runtime=runtime))
        context.save_posted_settings({"session_goal": "12"})
        self.assertEqual(calls.count(("POST", "dialer_settings")), 1)

    def test_signed_in_account_ignores_server_twilio_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "TWILIO_ACCOUNT_SID=ACserver\nTWILIO_AUTH_TOKEN=server-token\n"
                "TWILIO_API_SECRET=server-secret\nTWILIO_TWIML_APP_SID=APserver\n"
                "PUBLIC_BASE_URL=https://server.example\nSESSION_GOAL=33\n",
                encoding="utf-8",
            )
            crm = ProspectStore(Path(directory) / "crm.json")
            with mock.patch.dict(os.environ, {"TWILIO_API_KEY": "SKenvironment"}):
                local = Dialer(crm, str(env_path))
                self.assertEqual(local.settings_state()["account_sid"], "ACserver")
                self.assertEqual(local.settings_state()["api_key"], "SKenvironment")

                dialer = Dialer(crm, str(env_path))
                dialer.account_user_id = "user-1"
                shown = dialer.settings_state()
                values = dialer.read_values()
            self.assertEqual(shown["account_sid"], "")
            self.assertEqual(shown["auth_token"], "")
            self.assertFalse(shown["has_auth_token"])
            self.assertFalse(shown["has_api_secret"])
            self.assertEqual(shown["api_key"], "")
            self.assertEqual(shown["twiml_app_sid"], "")
            self.assertEqual(shown["public_base_url"], "")
            self.assertEqual(shown["session_goal"], 33)
            self.assertEqual(values["TWILIO_AUTH_TOKEN"], "")

    def test_supabase_without_anon_key_fails_at_startup(self):
        import features.accounts as accounts

        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "SUPABASE_URL=https://project.supabase.co\nSUPABASE_SECRET_KEY=sb_secret_test\n",
                encoding="utf-8",
            )
            cleared = {key: "" for key in ("SUPABASE_ANON_KEY", "SUPABASE_PUBLISHABLE_KEY")}
            with mock.patch.object(accounts, "ENV_PATH", str(env_path)), mock.patch.dict(os.environ, cleared):
                with self.assertRaisesRegex(ValueError, "SUPABASE_ANON_KEY is required when Supabase storage is configured"):
                    accounts.AppRuntime().configure()
