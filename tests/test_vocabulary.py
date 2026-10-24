import re
import unittest
from pathlib import Path

from shared.vocabulary import CRM_STATUS_KEYS, METRIC_KEYS, browser_vocabulary, canonical_status, parse_prospect_status

ROOT = Path(__file__).resolve().parent.parent


class VocabularyTests(unittest.TestCase):
    def test_canonical_status_defaults_missing_to_new(self):
        self.assertEqual(canonical_status(None), "new")
        self.assertEqual(canonical_status(""), "new")
        self.assertEqual(canonical_status("interested"), "disqualified")
        self.assertEqual(parse_prospect_status("Not interested"), "disqualified")
        self.assertEqual(parse_prospect_status("Send info"), "send_info")
        self.assertEqual(parse_prospect_status("Callback (12 hour timer)"), "call")
        self.assertEqual(parse_prospect_status("No answer (disqualified)"), "no_answer_disqualified")

    def test_browser_vocabulary_includes_crm_status_menu(self):
        payload = browser_vocabulary()
        self.assertEqual(payload["crmStatusKeys"], list(CRM_STATUS_KEYS))
        self.assertIn("call", payload["crmStatusLabels"])
        self.assertEqual(payload["crmStatusKeys"][0], "new")

    def test_schema_metric_key_lists_match_vocabulary(self):
        text = (ROOT / "docs" / "supabase" / "schema.sql").read_text(encoding="utf-8")
        lists = re.findall(
            r"(?:metric_key in|p_metric_key not in) \(\s*(.*?)\)",
            text,
            flags=re.I | re.S,
        )
        self.assertEqual(len(lists), 5)
        expected = tuple(METRIC_KEYS)
        for block in lists:
            found = tuple(re.findall(r"'([^']+)'", block))
            self.assertEqual(found, expected)
