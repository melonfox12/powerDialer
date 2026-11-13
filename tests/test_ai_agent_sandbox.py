import base64
import unittest
from unittest.mock import patch

from features import ai_agent_playbook, ai_agent_sandbox
from features._dialer.state import DialerState


class StubCrm:
    def snapshot(self):
        return []


class SandboxTests(unittest.TestCase):
    def _state(self):
        state = DialerState(StubCrm(), ".env")
        state.settings = {"OPENAI_API_KEY": "test", "AI_LLM_MODEL": "gpt-4o-mini"}
        state.read_settings = lambda: dict(state.settings)
        state.record_activity = lambda *args, **kwargs: None
        ai_agent_playbook.save_playbook(state, "ava", {"prompt": "Sandbox test prompt."}, "Ava")
        return state

    @patch("features.ai_agent_sandbox.ai_voice_cartesia.tts_sandbox_stream", return_value="")
    @patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", side_effect=["Hello from Ava", "Sure, tell me more."])
    def test_start_and_turn(self, _llm, _tts):
        import time

        state = self._state()
        opened = ai_agent_sandbox.start(state, "ava", {"name": "Pat"})
        self.assertTrue(opened["active"])
        ai_agent_sandbox.mark_playback_ready(state, "ava")
        snapshot = opened
        for _ in range(40):
            snapshot = ai_agent_sandbox.stream_sync(state, "ava")
            if len(snapshot.get("transcript") or []) >= 1 and snapshot.get("chunks"):
                break
            time.sleep(0.02)
        self.assertEqual(len(snapshot["transcript"]), 1)
        self.assertEqual(snapshot["transcript"][0]["speaker"], "Agent")

        def _stream(_settings, _text, emit, **_kw):
            emit("qq==")
            emit("qw==")
            return ""

        with patch("features.ai_agent_sandbox.ai_voice_cartesia.tts_sandbox_stream", side_effect=_stream):
            reply = ai_agent_sandbox.turn(state, "ava", "Not a great time.")
        self.assertEqual(len(reply["transcript"]), 3)
        self.assertEqual(reply["transcript"][-1]["speaker"], "Agent")
        for _ in range(30):
            if state.ai_sandbox_sessions.get("ava", {}).get("outbound_chunks"):
                break
            time.sleep(0.02)
        self.assertTrue(state.ai_sandbox_sessions["ava"]["outbound_chunks"])

    def test_undelivered_opening_reaches_sync(self):
        import time

        state = self._state()
        def _stream(_s, _t, emit):
            emit("qq==")
            return ""

        with patch("features.ai_agent_sandbox.ai_voice_cartesia.tts_sandbox_stream", side_effect=_stream):
            with patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", return_value="Hi there"):
                ai_agent_sandbox.start(state, "ava", None)
                ai_agent_sandbox.mark_playback_ready(state, "ava")
                for _ in range(50):
                    if state.ai_sandbox_sessions.get("ava", {}).get("booting") is False:
                        break
                    time.sleep(0.02)
                sync = ai_agent_sandbox.stream_sync(state, "ava")
                self.assertEqual(sync["chunks"], ["qq=="])

    def test_reset(self):
        state = self._state()
        with patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", return_value="Hi"):
            ai_agent_sandbox.start(state, "ava", None)
            ai_agent_sandbox.mark_playback_ready(state, "ava")
        cleared = ai_agent_sandbox.reset(state, "ava")
        self.assertFalse(cleared["active"])
        self.assertEqual(state.ai_sandbox_sessions, {})

    def test_blocks_while_dialing(self):
        state = self._state()
        state.running = True
        with self.assertRaises(ValueError):
            ai_agent_sandbox.start(state, "ava", None)

    @patch("features.ai_agent_sandbox.ai_voice_cartesia.tts_sandbox_stream", return_value="")
    @patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", return_value="Hi")
    @patch("features.ai_agent_sandbox.ai_voice_stt.transcribe_mulaw", return_value="hello there")
    def test_ingest_flushes_after_speech(self, _stt, _llm, _tts):
        import time

        state = self._state()
        ai_agent_sandbox.start(state, "ava", None)
        ai_agent_sandbox.mark_playback_ready(state, "ava")
        for _ in range(40):
            if state.ai_sandbox_sessions.get("ava", {}).get("booting") is False:
                break
            time.sleep(0.02)
        loud = bytes([0x00, 0x80] * 200)
        silence = bytes([0xFF] * 160)
        payload = loud + silence * 25
        ai_agent_sandbox.ingest_mulaw(state, "ava", base64.b64encode(payload).decode())
        import time
        time.sleep(0.05)
        session = state.ai_sandbox_sessions["ava"]
        speakers = [line["speaker"] for line in session["transcript"]]
        self.assertIn("Prospect", speakers)


if __name__ == "__main__":
    unittest.main()
