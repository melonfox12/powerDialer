import re
import unittest
from pathlib import Path

from shared.vocabulary import METRIC_KEYS

ROOT = Path(__file__).resolve().parent.parent


class VocabularyTests(unittest.TestCase):
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
