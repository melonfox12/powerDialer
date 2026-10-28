import json
import tempfile
import unittest
from pathlib import Path

from features._prospects.csv_import import build_manual_lead, parse_csv
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

    def test_field_update_normalizes_phone_and_keeps_other_data(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            crm.save()
            updated = crm.update_fields("prospect-1", {
                "name": "Ada Lovelace",
                "business": "Analytical Engines",
                "phone": "12025550199",
                "timezone": "pst",
                "fields": {"City": "London", "Notes": "Call after 2"},
            })
            self.assertEqual(updated["phone"], "+12025550199")
            self.assertEqual(updated["timezone"], "Pacific")
            self.assertEqual(updated["status"], "new")
            self.assertEqual(updated["transcript"], [])
            cleared = crm.update_fields("prospect-1", {"fields": {"Notes": ""}})
            self.assertEqual(cleared["fields"], {"City": "London"})
            saved = ProspectStore(Path(directory) / "crm.json").snapshot()[0]
            self.assertEqual(saved["name"], "Ada Lovelace")
            self.assertEqual(saved["fields"], {"City": "London"})

    def test_field_update_rejects_bad_and_duplicate_phones(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            crm.save()
            crm.add_lead({"phone": "2025550188", "name": "Grace"})
            with self.assertRaises(ValueError):
                crm.update_fields("prospect-1", {"phone": "not a phone"})
            with self.assertRaises(ValueError):
                crm.update_fields("prospect-1", {"phone": "2025550188"})
            saved = crm.snapshot()
            original = next(lead for lead in saved if lead["id"] == "prospect-1")
            self.assertEqual(original["phone"], "+12025550123")
            self.assertEqual(original["name"], "Onyx")

    def test_scraper_csv_maps_columns_and_keeps_blank_numbers_null(self):
        sample = """Fit,Prospect,Company,State,City,Phone Number,Timezone,Total Reviews,Reviews (Last 30 Days),Days Since Last Review,30-Day %,Recency Source
Ideal,Mike,Mike's Pest Control,CA,San Francisco,(415) 555-1234,Pacific,142,5,3,3.5,exact
Size fit – recency unknown,,Bay Area Exterminators,CA,Oakland,(510) 555-9876,Pacific,88,,,,
Too large,,Orkin,CA,San Jose,(408) 555-0000,Pacific,1495,12,1,0.8,exact
"""
        leads, info = parse_csv(sample)
        self.assertEqual(len(leads), 3)
        self.assertEqual(info["skipped"], 0)
        mike, bay, orkin = leads
        self.assertEqual(mike["name"], "Mike")
        self.assertEqual(mike["business_type"], "pest control")
        self.assertEqual(mike["business"], "Mike's Pest Control")
        self.assertEqual(mike["state"], "CA")
        self.assertEqual(mike["city"], "San Francisco")
        self.assertEqual(mike["phone"], "+14155551234")
        self.assertEqual(mike["timezone"], "Pacific")
        self.assertEqual(mike["review_count"], 142)
        self.assertEqual(mike["reviews_last_30_days"], 5)
        self.assertEqual(mike["days_since_last_review"], 3)
        self.assertEqual(mike["review_pct_30_days"], 3.5)
        self.assertEqual(mike["recency_source"], "exact")
        self.assertNotIn("Fit", mike["fields"])
        self.assertNotIn("Total Reviews", mike["fields"])
        self.assertEqual(bay["name"], "")
        self.assertEqual(bay["business"], "Bay Area Exterminators")
        self.assertEqual(bay["review_count"], 88)
        self.assertIsNone(bay["reviews_last_30_days"])
        self.assertIsNone(bay["days_since_last_review"])
        self.assertIsNone(bay["review_pct_30_days"])
        self.assertIsNone(bay["recency_source"])
        self.assertEqual(orkin["name"], "")
        self.assertEqual(orkin["review_count"], 1495)
        self.assertEqual(orkin["reviews_last_30_days"], 12)
        self.assertEqual(orkin["days_since_last_review"], 1)
        self.assertEqual(orkin["review_pct_30_days"], 0.8)
        self.assertEqual(orkin["recency_source"], "exact")
        messy, _info = parse_csv(
            " FIT , prospect ,Company, phone number ,Total Reviews,Reviews (Last 30 Days),Notes\n"
            "Ideal,Ann,Ann Co,(716) 555-1212,10,,VIP\n"
        )
        self.assertEqual(messy[0]["name"], "Ann")
        self.assertEqual(messy[0]["review_count"], 10)
        self.assertIsNone(messy[0]["reviews_last_30_days"])
        self.assertEqual(messy[0]["fields"].get("Notes"), "VIP")
        self.assertNotIn("FIT", messy[0]["fields"])
        self.assertNotIn("Fit", messy[0]["fields"])

    def test_csv_business_type_column_and_default(self):
        typed, _info = parse_csv(
            b"Business Type,Prospect,Company,Phone\nHVAC,Ada,Engines,2025550199\n"
        )
        self.assertEqual(typed[0]["business_type"], "HVAC")
        default, _info = parse_csv(b"Prospect,Company,Phone\nAda,Engines,2025550199\n")
        self.assertEqual(default[0]["business_type"], "pest control")

    def test_store_backfills_missing_business_type_on_load(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crm.json"
            crm = ProspectStore(path)
            crm.leads = [prospect()]
            crm.save()
            self.assertNotIn("business_type", crm.leads[0])
            reloaded = ProspectStore(path)
            saved = json.loads(path.read_text(encoding="utf-8"))[0]
            self.assertEqual(saved["business_type"], "pest control")
            self.assertEqual(reloaded.snapshot()[0]["business_type"], "pest control")

    def test_csv_state_and_city_become_their_own_columns(self):
        leads, _info = parse_csv(
            b"Name,Company,State,City,Phone,Notes\nAda,Engines,Virginia,Arlington,2025550199,VIP\n"
        )
        lead = leads[0]
        self.assertEqual(lead["state"], "Virginia")
        self.assertEqual(lead["city"], "Arlington")
        self.assertEqual(lead["business"], "Engines")
        self.assertEqual(lead["fields"], {"Name": "Ada", "Company": "Engines", "Phone": "2025550199", "Notes": "VIP"})
        untouched, _info = parse_csv(b"Name,Status,Phone\nBea,new,2025550188\n")
        self.assertEqual(untouched[0]["state"], "")
        self.assertEqual(untouched[0]["city"], "")

    def test_editing_city_replaces_an_older_city_column(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            crm.leads[0]["fields"] = {"City": "London", "Notes": "VIP"}
            crm.save()
            updated = crm.update_fields("prospect-1", {"city": "Paris", "state": "Texas"})
            self.assertEqual(updated["city"], "Paris")
            self.assertEqual(updated["state"], "Texas")
            self.assertEqual(updated["fields"], {"Notes": "VIP"})

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

    def test_supabase_update_fields_writes_the_cache(self):
        client = FakeSupabaseClient(prospect())
        client.users["prospect-1"] = "user-a"
        crm = ProspectStore(client=client, user_id="user-a")
        updated = crm.update_fields("prospect-1", {"business": "Navy", "timezone": "Central"})
        self.assertEqual(updated["business"], "Navy")
        self.assertEqual(crm.snapshot()[0]["timezone"], "Central")
        self.assertEqual(client.leads["prospect-1"]["timezone"], "Central")


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
        with self.assertRaises(OSError):
            crm.update_fields("prospect-1", {"name": "Changed"})
        cached = crm.snapshot()[0]
        self.assertEqual(cached["name"], "Onyx")
        self.assertEqual(cached["status"], "new")
        self.assertEqual(cached["transcript"], [])
        self.assertNotIn("call_log", cached)

    def test_successful_write_updates_the_cache(self):
        client = FakeSupabaseClient(prospect())
        crm = ProspectStore(client=client)
        crm.set_status("prospect-1", "do_not_call")
        crm.append_transcript("prospect-1", {"id": "s1", "speaker": "Agent", "text": "Hello"})
        cached = crm.snapshot()[0]
        self.assertEqual(cached["status"], "disqualified")
        self.assertEqual(cached["transcript"][0]["text"], "Hello")
        self.assertEqual(client.leads["prospect-1"]["status"], "disqualified")

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


class DialCapTests(unittest.TestCase):
    def test_fifth_call_log_entry_marks_no_answer_disqualified(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            for index in range(4):
                crm.append_call_log("prospect-1", {"id": f"dial-{index}", "started_at": f"2026-01-0{index + 1}T12:00:00+00:00"})
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            crm.append_call_log("prospect-1", {"id": "dial-4", "started_at": "2026-01-05T12:00:00+00:00"})
            self.assertEqual(crm.snapshot()[0]["status"], "no_answer_disqualified")

    def test_connected_dial_does_not_trigger_no_answer_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            for index in range(5):
                crm.append_call_log(
                    "prospect-1",
                    {
                        "id": f"dial-{index}",
                        "started_at": f"2026-01-0{index + 1}T12:00:00+00:00",
                        "connected": index == 2,
                    },
                )
            self.assertEqual(crm.snapshot()[0]["status"], "new")

    def test_enforce_dial_caps_backfills_prospects_already_at_five_dials(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = prospect()
            lead["call_log"] = [
                {"id": "dial-1", "started_at": "2026-01-01T12:00:00+00:00"},
                {"id": "dial-2", "started_at": "2026-01-02T12:00:00+00:00"},
                {"id": "dial-3", "started_at": "2026-01-03T12:00:00+00:00"},
                {"id": "dial-4", "started_at": "2026-01-04T12:00:00+00:00"},
                {"id": "dial-5", "started_at": "2026-01-05T12:00:00+00:00"},
            ]
            crm.leads = [lead]
            result = crm.enforce_dial_caps()
            self.assertEqual(result["capped"], 1)
            self.assertEqual(crm.snapshot()[0]["status"], "no_answer_disqualified")
            self.assertEqual(crm.enforce_dial_caps()["capped"], 0)

    def test_repair_resets_wrong_disqualified_without_live_contact(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = prospect()
            lead["status"] = "disqualified"
            lead["call_log"] = [{"id": "dial-1", "started_at": "2026-01-01T12:00:00+00:00"}]
            crm.leads = [lead]
            result = crm.enforce_dial_caps(repair_misclassified=True)
            self.assertEqual(result["to_new"], 1)
            self.assertEqual(crm.snapshot()[0]["status"], "new")

    def test_repair_keeps_disqualified_when_transcript_exists(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = prospect()
            lead["status"] = "disqualified"
            lead["transcript"] = [{"id": "s1", "speaker": "Agent", "text": "Hi", "timestamp": "2026-01-01T12:00:00+00:00"}]
            crm.leads = [lead]
            result = crm.enforce_dial_caps(repair_misclassified=True)
            self.assertEqual(result["to_new"], 0)
            self.assertEqual(crm.snapshot()[0]["status"], "disqualified")

    def test_booked_prospects_are_not_moved_to_disqualified_by_the_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = prospect()
            lead["status"] = "booked"
            lead["booked_at"] = "2026-01-01T12:00:00+00:00"
            lead["call_log"] = [
                {"id": "dial-1", "started_at": "2026-01-01T12:00:00+00:00"},
                {"id": "dial-2", "started_at": "2026-01-02T12:00:00+00:00"},
            ]
            crm.leads = [lead]
            self.assertEqual(crm.enforce_dial_caps()["capped"], 0)
            self.assertEqual(crm.snapshot()[0]["status"], "booked")


if __name__ == "__main__":
    unittest.main()
