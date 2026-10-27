import csv
import tempfile
import unittest
from io import StringIO
from pathlib import Path

from features._prospects.dial_archive import DialArchiveStore, dials_export_rows
from features._prospects.dials_csv_export import dials_csv_bytes_for
from features.prospects import ProspectStore


class DialArchiveTests(unittest.TestCase):
    def test_delete_archives_call_log_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            lead = crm.add_lead({
                "name": "Ada",
                "business": "Shop",
                "phone": "+12025550111",
                "timezone": "Eastern",
            })
            crm.append_call_log(lead["id"], {
                "id": "CA123",
                "started_at": "2026-10-26T12:00:00+00:00",
                "ended_at": "2026-10-26T12:01:00+00:00",
                "caller_id": "+18607354163",
                "answered_by": "human",
                "duration_seconds": 42,
                "transcript_lines": 1,
                "connected": True,
            })
            lead = crm.snapshot()[0]
            archive.archive_lead(lead)
            crm.remove(lead["id"])
            self.assertEqual(crm.snapshot(), [])
            records = archive.snapshot()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["name"], "Ada")
            self.assertEqual(records[0]["entry"]["id"], "CA123")

    def test_export_includes_archived_rows_after_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            lead = crm.add_lead({
                "name": "Ada",
                "phone": "+12025550111",
                "timezone": "Eastern",
            })
            crm.append_call_log(lead["id"], {
                "id": "CA123",
                "started_at": "2026-10-26T12:00:00+00:00",
                "ended_at": "2026-10-26T12:01:00+00:00",
            })
            archive.archive_lead(crm.snapshot()[0])
            crm.remove(lead["id"])
            decoded = dials_csv_bytes_for([], archive.snapshot()).decode("utf-8-sig")
            rows = list(csv.DictReader(StringIO(decoded)))
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["Prospect"], "Ada")
            self.assertEqual(rows[0]["dial_id"], "CA123")

    def test_import_restores_archived_dial_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            csv_bytes = dials_csv_bytes_for([], [{
                "id": "lead-1:CA999",
                "lead_id": "lead-1",
                "name": "Removed",
                "phone": "+12025550199",
                "business": "Gone",
                "review_count": 4,
                "timezone": "Eastern",
                "status": "new",
                "transcript": [],
                "entry": {
                    "id": "CA999",
                    "started_at": "2026-10-26T13:00:00+00:00",
                    "ended_at": "2026-10-26T13:02:00+00:00",
                    "caller_id": "",
                    "answered_by": "human",
                    "duration_seconds": 30,
                    "transcript_lines": 0,
                    "connected": True,
                    "outcome": None,
                },
            }])
            result = archive.import_csv_bytes(csv_bytes, crm=crm)
            self.assertEqual(result["added_archive"], 1)
            self.assertEqual(len(dials_export_rows(crm.snapshot(), archive.snapshot())), 1)


if __name__ == "__main__":
    unittest.main()
