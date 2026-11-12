import unittest

from features.ai_agent_playbook import (
    compile_playbook,
    default_playbook,
    legacy_dict_to_prompt,
    normalize_playbook,
    save_playbook,
)


class PlaybookStub:
    def __init__(self):
        self.settings = {}
        self.account_values = {}

    def read_settings(self):
        return dict(self.settings)


class PlaybookTests(unittest.TestCase):
    def test_default_is_single_prompt(self):
        book = default_playbook("Ava")
        self.assertTrue(book["prompt"])
        self.assertEqual(book["compiled"]["system_prompt"], book["prompt"])

    def test_legacy_flattens_to_prompt(self):
        text = legacy_dict_to_prompt({
            "title": "Test",
            "objective": "Book meetings",
            "steps": [{"label": "Intro", "dialogue": "Hi", "actions": "Smile"}],
        })
        self.assertIn("Book meetings", text)
        self.assertIn("Intro", text)

    def test_compile_on_save(self):
        stub = PlaybookStub()
        saved = save_playbook(stub, "ava", {"prompt": "Say hello and qualify."})
        self.assertEqual(saved["compiled"]["system_prompt"], "Say hello and qualify.")

    def test_normalize_string_payload(self):
        book = normalize_playbook("Raw prompt line", "Ava")
        self.assertEqual(book["prompt"], "Raw prompt line")


if __name__ == "__main__":
    unittest.main()
