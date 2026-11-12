import json
import unittest

from features.ai_agent_playbook import (
    compile_playbook,
    default_playbook,
    get_playbook,
    legacy_dict_to_prompt,
    normalize_playbook,
    save_playbook,
)
from shared.vocabulary import AI_AGENT_PLAYBOOKS_JSON_KEY


class PlaybookStub:
    def __init__(self):
        self.settings = {}
        self.account_values = {}
        self.saved = False

    def read_settings(self):
        return dict(self.settings)

    def settings_saver(self, state):
        self.saved = True


class PlaybookTests(unittest.TestCase):
    def test_default_is_single_prompt(self):
        book = default_playbook("Ava")
        self.assertTrue(book["prompt"])
        self.assertIn("[Agent seat: Ava]", book["compiled"]["system_prompt"])
        self.assertTrue(book["execution_ready"])

    def test_legacy_flattens_to_prompt(self):
        text = legacy_dict_to_prompt({
            "title": "Test",
            "objective": "Book meetings",
            "steps": [{"label": "Intro", "dialogue": "Hi", "actions": "Smile"}],
        })
        self.assertIn("Book meetings", text)
        self.assertIn("Intro", text)

    def test_compile_on_save_persists_baked_prompt(self):
        stub = PlaybookStub()
        saved = save_playbook(stub, "ava", {"prompt": "Say hello and qualify."})
        self.assertTrue(saved["execution_ready"])
        self.assertIn("Say hello and qualify.", saved["compiled"]["system_prompt"])
        self.assertIn("[END_CALL]", saved["compiled"]["system_prompt"])
        raw = json.loads(stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY])
        stored = raw["playbooks"]["ava"]
        self.assertIn("compiled", stored)
        self.assertEqual(stored["compiled"]["prompt_digest"], saved["compiled"]["prompt_digest"])
        stub.saved = False

    def test_get_uses_stored_compile_without_rebaking(self):
        stub = PlaybookStub()
        save_playbook(stub, "ava", {"prompt": "My stable prompt."})
        blob = json.loads(stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY])
        blob["playbooks"]["ava"]["compiled"]["system_prompt"] = "[Agent seat: Ava]\n\nBaked marker"
        stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY] = json.dumps(blob)
        loaded = get_playbook(stub, "ava", "Ava")
        self.assertTrue(loaded["execution_ready"])
        self.assertIn("Baked marker", loaded["compiled"]["system_prompt"])

    def test_get_marks_draft_when_prompt_changed_locally(self):
        stub = PlaybookStub()
        save_playbook(stub, "ava", {"prompt": "Version one."})
        blob = json.loads(stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY])
        blob["playbooks"]["ava"]["prompt"] = "Version two."
        stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY] = json.dumps(blob)
        loaded = get_playbook(stub, "ava", "Ava")
        self.assertFalse(loaded["execution_ready"])

    def test_require_ready_blocks_uncompiled(self):
        stub = PlaybookStub()
        save_playbook(stub, "ava", {"prompt": "Version one."})
        blob = json.loads(stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY])
        blob["playbooks"]["ava"]["prompt"] = "Draft edit."
        stub.settings[AI_AGENT_PLAYBOOKS_JSON_KEY] = json.dumps(blob)
        with self.assertRaises(ValueError):
            get_playbook(stub, "ava", "Ava", require_ready=True)

    def test_normalize_string_payload(self):
        book = normalize_playbook("Raw prompt line", "Ava")
        self.assertEqual(book["prompt"], "Raw prompt line")

    def test_compile_resolves_agent_name_placeholder(self):
        compiled = compile_playbook({"prompt": "You are {agent_name}."}, "Ava")
        self.assertIn("You are Ava.", compiled["system_prompt"])


if __name__ == "__main__":
    unittest.main()
