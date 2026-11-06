import unittest

from shared.pipeline_config import normalize_pipeline_step_key


class NormalizePipelineStepKeyTests(unittest.TestCase):
    def test_lowercase_and_underscores(self):
        self.assertEqual(normalize_pipeline_step_key("Follow Up"), "follow_up")

    def test_punctuation_split_words(self):
        self.assertEqual(normalize_pipeline_step_key("Email #1"), "email_1")

    def test_leading_digits(self):
        self.assertEqual(normalize_pipeline_step_key("123"), "step_123")

    def test_empty(self):
        self.assertEqual(normalize_pipeline_step_key("   ---   "), "")

    def test_preserves_valid_key(self):
        self.assertEqual(normalize_pipeline_step_key("email_1"), "email_1")


if __name__ == "__main__":
    unittest.main()
