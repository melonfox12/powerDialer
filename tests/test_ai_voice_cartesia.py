import json
import unittest
from io import BytesIO
from unittest import mock

from features import ai_voice_cartesia


class CartesiaVoiceTests(unittest.TestCase):
    def test_voice_uuid_in_request_body(self):
        settings = {
            "CARTESIA_API_KEY": "sk_test",
            "CARTESIA_VOICE_ID": "607167f6-9bf2-473c-accc-ac7b3b66b30b",
        }
        captured = {}

        def fake_open(request, timeout=60):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return BytesIO(b"\x00\x01")

        with mock.patch("urllib.request.urlopen", side_effect=fake_open):
            chunks, err = ai_voice_cartesia.tts_sandbox_chunks(settings, "Hello")
        self.assertEqual(err, "")
        self.assertTrue(chunks)
        self.assertEqual(
            captured["body"]["voice"],
            "607167f6-9bf2-473c-accc-ac7b3b66b30b",
        )
        self.assertNotIn("mode", captured["body"]["voice"])

    def test_invalid_voice_falls_back_to_default(self):
        settings = {"CARTESIA_API_KEY": "sk_test", "CARTESIA_VOICE_ID": "not-a-uuid"}
        captured = {}

        def fake_open(request, timeout=60):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return BytesIO(b"\x00\x01")

        with mock.patch("urllib.request.urlopen", side_effect=fake_open):
            ai_voice_cartesia.tts_sandbox_chunks(settings, "Hi")
        self.assertEqual(captured["body"]["voice"], ai_voice_cartesia._DEFAULT_VOICE_ID)


if __name__ == "__main__":
    unittest.main()
