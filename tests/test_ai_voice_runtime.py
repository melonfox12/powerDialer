import unittest

from features.ai_voice_runtime import (
    ai_stream_twiml,
    bridge_secret_ok,
    purge_sessions,
    start_call_session,
    voice_configured,
)
from features._dialer.state import DialerState


class StubCrm:
    def snapshot(self):
        return []

    def append_transcript(self, *args, **kwargs):
        pass


class VoiceRuntimeTests(unittest.TestCase):
    def _state(self):
        state = DialerState(StubCrm(), ".env")
        state.running = True
        state.ai_agent_mode = True
        state.ai_agent_id = "ava"
        state.voice_profile = "cartesia_line"
        state.ai_voice_armed = True
        state.public_base_url = "https://example.test"
        state.settings = {
            "AI_BRIDGE_SECRET": "test-secret",
            "AI_BRIDGE_WSS_URL": "wss://bridge.example/stream",
            "OPENAI_API_KEY": "",
            "CARTESIA_API_KEY": "",
        }
        state.read_settings = lambda: dict(state.settings)
        state.read_values = lambda: dict(state.settings)
        state.record_activity = lambda *args, **kwargs: None
        return state

    def test_bridge_secret(self):
        state = self._state()
        self.assertTrue(bridge_secret_ok(state, "test-secret"))
        self.assertFalse(bridge_secret_ok(state, "wrong"))

    def test_voice_configured(self):
        state = self._state()
        self.assertTrue(voice_configured(state.settings))
        state.settings["AI_BRIDGE_WSS_URL"] = ""
        self.assertFalse(voice_configured(state.settings))

    def test_twiml_without_bridge(self):
        state = self._state()
        state.settings["AI_BRIDGE_WSS_URL"] = ""
        call = {"token": "t", "bridge_session_id": "s1"}
        xml = ai_stream_twiml(state, call)
        self.assertIn("Say", xml)
        self.assertIn("Hangup", xml)

    def test_purge_sessions(self):
        state = self._state()
        state.ai_voice_sessions["x"] = {"session_id": "x", "ended": False, "messages": [], "lead_id": None}
        purge_sessions(state)
        self.assertEqual(state.ai_voice_sessions, {})

    def test_start_session_and_twiml(self):
        state = self._state()
        call = {
            "token": "tok1",
            "kind": "prospect",
            "lead_id": "L1",
            "lead": {"id": "L1", "name": "Pat", "business": "Acme"},
            "transcript_partials": {},
            "transcript_lines": [],
        }
        sid = start_call_session(state, call)
        self.assertTrue(sid)
        xml = ai_stream_twiml(state, call)
        self.assertIn("Stream", xml)
        self.assertIn(sid, xml)


if __name__ == "__main__":
    unittest.main()
