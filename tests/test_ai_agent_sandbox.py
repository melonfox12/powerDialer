import unittest
from unittest.mock import patch

from features import ai_agent_sandbox
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
        return state

    @patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", side_effect=["Hello from Ava", "Sure, tell me more."])
    def test_start_and_turn(self, _llm):
        state = self._state()
        opened = ai_agent_sandbox.start(state, "ava", {"name": "Pat"})
        self.assertTrue(opened["active"])
        self.assertEqual(len(opened["transcript"]), 1)
        self.assertEqual(opened["transcript"][0]["speaker"], "Agent")

        reply = ai_agent_sandbox.turn(state, "ava", "Not a great time.")
        self.assertEqual(len(reply["transcript"]), 3)
        self.assertEqual(reply["transcript"][-1]["speaker"], "Agent")

    def test_reset(self):
        state = self._state()
        with patch("features.ai_agent_sandbox.ai_voice_llm.chat_reply", return_value="Hi"):
            ai_agent_sandbox.start(state, "ava", None)
        cleared = ai_agent_sandbox.reset(state, "ava")
        self.assertFalse(cleared["active"])
        self.assertEqual(state.ai_sandbox_sessions, {})

    def test_blocks_while_dialing(self):
        state = self._state()
        state.running = True
        with self.assertRaises(ValueError):
            ai_agent_sandbox.start(state, "ava", None)


if __name__ == "__main__":
    unittest.main()
