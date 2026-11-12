import base64
import unittest
from unittest.mock import patch

from features import ai_voice_inbound
from features._dialer.state import DialerState


class StubCrm:
    def snapshot(self):
        return []


class InboundTests(unittest.TestCase):
    def _session_state(self):
        state = DialerState(StubCrm(), ".env")
        state.ai_voice_sessions["s1"] = {
            "session_id": "s1",
            "call_token": "tok",
            "ended": False,
            "inbound_mulaw": bytearray(),
            "silence_frames": 0,
            "heard_voice": False,
        }
        state.calls["tok"] = {"token": "tok", "bridge_session_id": "s1", "transcript_lines": []}
        state.settings = {}
        state.read_settings = lambda: {}
        return state

    def test_ingest_buffers_without_flush_on_short_chunk(self):
        state = self._session_state()
        chunk = base64.b64encode(bytes([255] * 100)).decode()
        ai_voice_inbound.ingest_mulaw(state, "s1", chunk)
        session = state.ai_voice_sessions["s1"]
        self.assertGreater(len(session["inbound_mulaw"]), 0)
        self.assertFalse(session.get("heard_voice"))

    @patch("features.ai_voice_inbound.ai_voice_stt.transcribe_mulaw", return_value="hello there")
    @patch("features.ai_voice_inbound.ai_voice_runtime.on_prospect_text")
    def test_utterance_flush_triggers_reply(self, on_text, _transcribe):
        state = self._session_state()
        session = state.ai_voice_sessions["s1"]
        loud = bytes([0x00] * 6000)
        session["inbound_mulaw"] = bytearray(loud)
        session["heard_voice"] = True
        session["silence_frames"] = ai_voice_inbound._SILENCE_FRAMES
        ai_voice_inbound._transcribe_and_reply(state, "s1", bytes(loud))
        on_text.assert_called_once()
        self.assertEqual(on_text.call_args[0][2], "hello there")


if __name__ == "__main__":
    unittest.main()
