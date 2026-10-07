import csv
import json
import tempfile
from pathlib import Path
from io import StringIO
from features.prospects import ProspectStore, parse_csv
from features.dialer import Dialer
from tests.test_transcript_storage.fixtures import FakeSupabaseClient
from tests.test_transcript_storage.fixtures import prospect

class Part1:
    def test_manual_prospect_is_saved_and_rejects_a_duplicate_phone(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = crm.add_lead({
                "name": "Ada Lovelace",
                "business": "Analytical Engines",
                "phone": "(202) 555-0142",
                "timezone": "Pacific",
                "status": "interested",
                "transcript": "Asked for a follow-up.",
                "fields": {"Email": "ada@example.com"},
            })
            self.assertEqual(lead["phone"], "+12025550142")
            self.assertEqual(lead["timezone"], "Pacific")
            saved = ProspectStore(Path(directory) / "crm.json").snapshot()[0]
            self.assertEqual(saved["name"], "Ada Lovelace")
            self.assertEqual(saved["business"], "Analytical Engines")
            self.assertEqual(saved["status"], "interested")
            self.assertEqual(saved["fields"]["Email"], "ada@example.com")
            self.assertEqual(saved["transcript"][0]["text"], "Asked for a follow-up.")
            with self.assertRaises(ValueError):
                crm.add_lead({"name": "Duplicate", "phone": "202-555-0142"})
            with self.assertRaises(ValueError):
                crm.add_lead({"name": "No phone"})

    def test_supabase_manual_prospect_is_stored(self):
        client = FakeSupabaseClient(prospect())
        crm = ProspectStore(client=client, user_id="user-a")
        lead = crm.add_lead({
            "name": "Grace Hopper",
            "business": "Navy",
            "phone": "4155550199",
            "status": "call",
        })
        self.assertEqual(lead["phone"], "+14155550199")
        self.assertEqual(lead["status"], "call")
        self.assertTrue(lead["scheduled_until"])
        self.assertEqual(client.leads[lead["id"]]["name"], "Grace Hopper")
        self.assertEqual(client.users[lead["id"]], "user-a")

    def test_local_transcript_is_persisted_and_exported_in_crm_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crm.json"
            crm = ProspectStore(path)
            crm.leads = [prospect()]
            crm.save()
            crm.append_transcript("prospect-1", {
                "id": "call-1:inbound:1",
                "timestamp": "2026-10-01T14:00:00+00:00",
                "speaker": "Prospect",
                "text": "Please send the estimate.",
            })

            reloaded = ProspectStore(path)
            self.assertEqual(reloaded.snapshot()[0]["transcript"][0]["text"], "Please send the estimate.")
            exported = csv.DictReader(StringIO(reloaded.csv_bytes().decode("utf-8-sig")))
            row = next(exported)
            self.assertEqual(
                row["Call transcript"],
                "2026-10-01T14:00:00+00:00 Prospect: Please send the estimate.",
            )

    def test_supabase_transcript_is_stored_with_prospect_data(self):
        client = FakeSupabaseClient(prospect())
        crm = ProspectStore(client=client)
        crm.append_transcript("prospect-1", {
            "id": "call-1:outbound:2",
            "timestamp": "2026-10-01T14:01:00+00:00",
            "speaker": "Agent",
            "text": "I'll send that over today.",
        })

        stored = client.leads["prospect-1"]
        self.assertEqual(stored["transcript"][0]["speaker"], "Agent")
        self.assertEqual(stored["transcript"][0]["text"], "I'll send that over today.")
        self.assertEqual(crm.snapshot()[0]["transcript"], stored["transcript"])

    def test_final_call_transcription_events_are_saved_to_the_prospect(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            call = dialer._new_call("prospect", prospect())
            dialer._transcription_event(call, {
                "TranscriptionEvent": "transcription-content",
                "TranscriptionData": json.dumps({"transcript": "Can you send the estimate?"}),
                "Track": "inbound_track",
                "Timestamp": "2026-10-01T14:00:00+00:00",
                "SequenceId": "7",
                "Final": "true",
            })

            saved = ProspectStore(Path(directory) / "crm.json").snapshot()[0]["transcript"]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["speaker"], "Prospect")
            self.assertEqual(saved[0]["text"], "Can you send the estimate?")

    def test_example_leads_csv_imports_phone_name_and_timezone(self):
        path = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "example_leads.csv"
        leads, info = parse_csv(path.read_bytes())
        self.assertGreaterEqual(len(leads), 1)
        self.assertEqual(info["skipped"], 0)
        self.assertTrue(leads[0]["phone"].startswith("+"))
        self.assertEqual(leads[0]["timezone"], "Eastern")
        self.assertEqual(leads[0]["name"], "Daniel Edwards")

    def test_local_csv_import_persists_prospects(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            info = crm.add_csv(b"Name,Business Name,Phone Number,Timezone\nAda,Co,(202) 555-0100,Pacific\n")
            self.assertEqual(info["added"], 1)
            saved = ProspectStore(Path(directory) / "crm.json").snapshot()[0]
            self.assertEqual(saved["phone"], "+12025550100")
            self.assertEqual(saved["timezone"], "Pacific")

    def test_supabase_csv_import_posts_prospect_rows(self):
        client = FakeSupabaseClient(prospect())
        crm = ProspectStore(client=client)
        info = crm.add_csv(b"Name,Phone\nSam,+1 202 555 0199\n")
        self.assertEqual(info["added"], 1)
        self.assertEqual(info["duplicates"], 0)
        imported = next(lead for lead in client.leads.values() if lead["phone"] == "+12025550199")
        self.assertEqual(imported["name"], "Sam")

    def test_supabase_csv_import_is_scoped_to_the_signed_in_user(self):
        client = FakeSupabaseClient(prospect())
        other = ProspectStore(client=client, user_id="user-b")
        other.add_csv(b"Name,Phone\nOther,+1 202 555 0101\n")
        mine = ProspectStore(client=client, user_id="user-a")
        info = mine.add_csv(b"Name,Phone\nMine,+1 202 555 0102\n")
        self.assertEqual(info["added"], 1)
        phones = [lead["phone"] for lead in mine.snapshot()]
        self.assertEqual(phones, ["+12025550102"])

    def test_a_directory_of_part_files_reloads_as_one_list(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crm_data"
            crm = ProspectStore(path)
            crm.leads = []
            for index in range(20):
                lead = prospect()
                lead["id"] = f"prospect-{index}"
                crm.leads.append(lead)
            crm.save()
            reloaded = ProspectStore(path)
            self.assertEqual([lead["id"] for lead in reloaded.leads], [f"prospect-{index}" for index in range(20)])
            parts = list(path.glob("*.json"))
            self.assertGreater(len(parts), 1)
            for part in parts:
                self.assertLessEqual(part.read_text(encoding="utf-8").count("\n"), 150)
