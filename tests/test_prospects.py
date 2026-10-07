import tempfile
import unittest
from pathlib import Path

from features._prospects.csv_import import build_manual_lead
from features.prospects import ProspectStore
from tests.test_transcript_storage.fixtures import FakeSupabaseClient, prospect


class ManualProspectTests(unittest.TestCase):
    def test_local_add_normalizes_phone_and_keeps_extra_columns(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = crm.add_lead({
                "name": "Ada Lovelace",
                "business": "Analytical Engines",
                "phone": "(202) 555-0199",
                "timezone": "est",
                "status": "new",
                "fields": {"City": "London", "Reviews": "12 reviews"},
            })
            saved = ProspectStore(Path(directory) / "crm.json").snapshot()[0]
            self.assertEqual(lead["phone"], "+12025550199")
            self.assertEqual(saved["name"], "Ada Lovelace")
            self.assertEqual(saved["business"], "Analytical Engines")
            self.assertEqual(saved["timezone"], "Eastern")
            self.assertEqual(saved["fields"]["City"], "London")
            self.assertEqual(saved["status"], "new")
            self.assertEqual(saved["transcript"], [])

    def test_duplicate_and_unusable_phone_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            crm.save()
            with self.assertRaises(ValueError):
                crm.add_lead({"phone": prospect()["phone"], "name": "Copy"})
            with self.assertRaises(ValueError):
                crm.add_lead({"phone": "not a phone", "name": "Nope"})
            self.assertEqual(len(crm.snapshot()), 1)

    def test_callback_status_schedules_a_follow_up(self):
        lead = build_manual_lead({
            "phone": "2025550100",
            "status": "call",
            "transcript": "Asked to call tomorrow.",
        })
        self.assertEqual(lead["status"], "call")
        self.assertTrue(lead["scheduled_until"])
        self.assertEqual(lead["transcript"][0]["text"], "Asked to call tomorrow.")

    def test_supabase_add_inserts_one_prospect(self):
        client = FakeSupabaseClient(prospect())
        client.users["prospect-1"] = "user-a"
        crm = ProspectStore(client=client, user_id="user-a")
        lead = crm.add_lead({
            "name": "Grace Hopper",
            "business": "Navy",
            "phone": "2025550188",
            "timezone": "Central",
            "fields": {"Rank": "Rear admiral"},
        })
        self.assertEqual(client.users[lead["id"]], "user-a")
        saved = crm.snapshot()
        self.assertEqual(len(saved), 2)
        added = next(item for item in saved if item["id"] == lead["id"])
        self.assertEqual(added["phone"], "+12025550188")
        self.assertEqual(added["fields"]["Rank"], "Rear admiral")


class FailingPatchClient(FakeSupabaseClient):
    def request(self, method, resource, params=None, payload=None, prefer=None):
        if method == "PATCH":
            raise OSError("Supabase HTTP 503")
        return super().request(method, resource, params, payload, prefer)


class SupabaseCacheTests(unittest.TestCase):
    def test_failed_write_leaves_the_cached_lead_unchanged(self):
        crm = ProspectStore(client=FailingPatchClient(prospect()))
        self.assertEqual(crm.snapshot()[0]["status"], "new")
        with self.assertRaises(OSError):
            crm.set_status("prospect-1", "do_not_call")
        with self.assertRaises(OSError):
            crm.append_transcript("prospect-1", {"id": "s1", "speaker": "Agent", "text": "Hello"})
        with self.assertRaises(OSError):
            crm.append_call_log("prospect-1", {"id": "c1", "duration_seconds": 5})
        cached = crm.snapshot()[0]
        self.assertEqual(cached["status"], "new")
        self.assertEqual(cached["transcript"], [])
        self.assertNotIn("call_log", cached)

    def test_successful_write_updates_the_cache(self):
        client = FakeSupabaseClient(prospect())
        crm = ProspectStore(client=client)
        crm.set_status("prospect-1", "do_not_call")
        crm.append_transcript("prospect-1", {"id": "s1", "speaker": "Agent", "text": "Hello"})
        cached = crm.snapshot()[0]
        self.assertEqual(cached["status"], "do_not_call")
        self.assertEqual(cached["transcript"][0]["text"], "Hello")
        self.assertEqual(client.leads["prospect-1"]["status"], "do_not_call")

    def test_csv_import_totals_match_between_backends(self):
        csv_body = b"Name,Phone\nBea,2025550112\nCy,2025550113\n"
        supabase = ProspectStore(client=FakeSupabaseClient(prospect()))
        with tempfile.TemporaryDirectory() as directory:
            local = ProspectStore(Path(directory) / "crm.json")
            local.leads = [prospect()]
            local.save()
            local_info = local.add_csv(csv_body)
        supabase_info = supabase.add_csv(csv_body)
        self.assertEqual(local_info["total"], 3)
        self.assertEqual(supabase_info, local_info)


if __name__ == "__main__":
    unittest.main()
