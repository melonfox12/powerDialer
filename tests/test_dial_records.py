import tempfile
import unittest
from pathlib import Path

from features._prospects.dial_archive import DialArchiveStore
from features._prospects.dial_records import DialRecordsStore, collect_active_dial_records, snapshot_active_dials
from features.prospects import ProspectStore


class DialRecordsTests(unittest.TestCase):
    def test_snapshot_saves_rows_and_clears_active_log(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            records = DialRecordsStore(crm_path=root / "crm")
            lead = crm.add_lead({
                "name": "Ada",
                "phone": "+12025550111",
                "timezone": "Eastern",
            })
            crm.append_call_log(lead["id"], {
                "id": "CA1",
                "started_at": "2026-10-26T12:00:00+00:00",
                "ended_at": "2026-10-26T12:01:00+00:00",
                "connected": True,
            })
            saved = snapshot_active_dials(crm, archive, records, title="Week one")
            self.assertEqual(saved["title"], "Week one")
            self.assertEqual(saved["dial_count"], 1)
            self.assertEqual(crm.snapshot()[0].get("call_log"), [])
            self.assertEqual(archive.snapshot(), [])
            summaries = records.list_summaries()
            self.assertEqual(len(summaries), 1)
            detail = records.get_record(saved["id"])
            self.assertEqual(len(detail["records"]), 1)
            self.assertEqual(detail["records"][0]["name"], "Ada")

    def test_snapshot_requires_at_least_one_dial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            records = DialRecordsStore(crm_path=root / "crm")
            crm.add_lead({"name": "Ada", "phone": "+12025550111", "timezone": "Eastern"})
            with self.assertRaises(ValueError):
                snapshot_active_dials(crm, archive, records)

    def test_collect_includes_archived_rows(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            crm = ProspectStore(root / "crm")
            archive = DialArchiveStore(crm_path=root / "crm")
            archived = [{
                "id": "lead-x:CA9",
                "lead_id": "lead-x",
                "name": "Removed",
                "phone": "+12025550199",
                "entry": {"id": "CA9", "started_at": "2026-10-26T13:00:00+00:00"},
            }]
            archive.replace_all(archived)
            rows = collect_active_dial_records(crm.snapshot(), archive.snapshot())
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["name"], "Removed")


if __name__ == "__main__":
    unittest.main()
