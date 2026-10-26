import csv
import unittest
from io import StringIO

from features._prospects.dials_csv_export import dials_csv_bytes_for


class DialsExportTests(unittest.TestCase):
    def test_csv_includes_table_and_call_log_columns(self):
        leads = [{
            "id": "lead-1",
            "name": "Ada",
            "phone": "+12025550111",
            "business": "Shop",
            "review_count": 12,
            "status": "new",
            "timezone": "Eastern",
            "transcript": [{"timestamp": "2026-10-26T12:00:00+00:00", "speaker": "Agent", "text": "Hi"}],
            "call_log": [{
                "id": "CA123",
                "started_at": "2026-10-26T12:00:00+00:00",
                "ended_at": "2026-10-26T12:01:00+00:00",
                "caller_id": "+18607354163",
                "answered_by": "human",
                "duration_seconds": 42,
                "transcript_lines": 3,
                "connected": True,
                "outcome": None,
            }],
        }]
        decoded = dials_csv_bytes_for(leads).decode("utf-8-sig")
        rows = list(csv.DictReader(StringIO(decoded)))
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["Prospect"], "Ada")
        self.assertEqual(row["Phone"], "+12025550111")
        self.assertEqual(row["dial_id"], "CA123")
        self.assertEqual(row["answered_by"], "human")
        self.assertEqual(row["duration_seconds"], "42")
        self.assertEqual(row["connected"], "true")
        self.assertEqual(row["Call transcript"], "1")


if __name__ == "__main__":
    unittest.main()
