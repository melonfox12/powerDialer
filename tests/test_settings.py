import tempfile
import unittest
from pathlib import Path

from crm_store import CRMStore
from features.settings import load_app_settings, preferences, save_app_settings
from shared.vocabulary import SETTING_DEFAULTS
from twilio_calls import TwilioDialer


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
            shown = dialer.settings_state()
            self.assertEqual(shown["auth_token"], "token")
            self.assertEqual(shown["api_secret"], "secret")
            dialer.save_settings({
                "account_sid": "ACexample",
                "auth_token": "",
                "api_key": "SKexample",
                "api_secret": "",
                "twiml_app_sid": "APexample",
                "public_base_url": "https://example.ngrok.dev",
            })
            kept = dialer.settings_state()
            self.assertEqual(kept["auth_token"], "token")
            self.assertEqual(kept["api_secret"], "secret")
            dialer.save_settings({"auth_token": "replaced-token", "api_secret": "replaced-secret", "account_sid": "ACexample", "api_key": "SKexample", "twiml_app_sid": "APexample", "public_base_url": "https://example.ngrok.dev"})
            replaced = dialer.settings_state()
            self.assertEqual(replaced["auth_token"], "replaced-token")
            self.assertEqual(replaced["api_secret"], "replaced-secret")
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
