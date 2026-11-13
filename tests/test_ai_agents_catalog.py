import unittest

from features import ai_agent_playbook, ai_agents
from features._dialer.state import DialerState


class StubCrm:
    def snapshot(self):
        return []


class AgentCatalogTests(unittest.TestCase):
    def _state(self):
        state = DialerState(StubCrm(), ".env")
        state.read_settings = lambda: dict(state.settings)
        state.record_activity = lambda *args, **kwargs: None
        return state

    def test_create_duplicate_delete(self):
        state = self._state()
        created = ai_agents.create_agent(state, "Taylor", "Qualifier")
        agent_id = created["agent"]["id"]
        self.assertTrue(agent_id)
        self.assertEqual(created["agent"]["name"], "Taylor")

        ai_agent_playbook.save_playbook(
            state,
            agent_id,
            {"prompt": "Custom prompt for Taylor."},
            "Taylor",
        )

        dup = ai_agents.duplicate_agent(state, agent_id)
        copy_id = dup["agent"]["id"]
        self.assertNotEqual(copy_id, agent_id)
        copy_playbook = ai_agent_playbook.get_playbook(state, copy_id, dup["agent"]["name"])
        self.assertIn("Custom prompt", copy_playbook["prompt"])

        view = ai_agents.agents_public_view(state)
        self.assertGreaterEqual(len(view["agents"]), 9)

        deleted = ai_agents.delete_agent(state, copy_id)
        self.assertEqual(deleted["deleted"], copy_id)
        blob = ai_agent_playbook._load_blob(state)
        self.assertNotIn(copy_id, blob.get("playbooks", {}))

    def test_cannot_delete_last_agent(self):
        state = self._state()
        blob = ai_agents._load_agents_data(state)
        blob["agents"] = [{"id": "solo", "name": "Solo", "title": "Test", "primary": True}]
        blob["pools"] = {"solo": []}
        ai_agents._save_agents_data(state, blob)
        with self.assertRaises(ValueError):
            ai_agents.delete_agent(state, "solo")


if __name__ == "__main__":
    unittest.main()
