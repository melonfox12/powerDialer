import csv
import json
import tempfile
from pathlib import Path
from io import StringIO
from crm_store import CRMStore, parse_csv
from supabase_store import SupabaseCRMStore
from twilio_calls import TwilioDialer
from tests.test_transcript_storage.fixtures import FakeSupabaseClient
from tests.test_transcript_storage.fixtures import prospect

class Part1:
    def test_local_transcript_is_persisted_and_exported_in_crm_csv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "crm.json"
            crm = CRMStore(path)
            crm.leads = [prospect()]
            crm.save()
            crm.append_transcript("prospect-1", {
                "id": "call-1:inbound:1",
                "timestamp": "2026-10-01T14:00:00+00:00",
                "speaker": "Prospect",
                "text": "Please send the estimate.",
            })

            reloaded = CRMStore(path)
            self.assertEqual(reloaded.snapshot()[0]["transcript"][0]["text"], "Please send the estimate.")
            exported = csv.DictReader(StringIO(reloaded.csv_bytes().decode("utf-8-sig")))
            row = next(exported)
            self.assertEqual(
                row["Call transcript"],
                "2026-10-01T14:00:00+00:00 Prospect: Please send the estimate.",
            )

    def test_supabase_transcript_is_stored_with_prospect_data(self):
        client = FakeSupabaseClient(prospect())
        crm = SupabaseCRMStore(client)
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
            crm = CRMStore(Path(directory) / "crm.json")
            crm.leads = [prospect()]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            call = dialer._new_call("prospect", prospect())
            dialer._transcription_event(call, {
                "TranscriptionEvent": "transcription-content",
                "TranscriptionData": json.dumps({"transcript": "Can you send the estimate?"}),
                "Track": "inbound_track",
                "Timestamp": "2026-10-01T14:00:00+00:00",
                "SequenceId": "7",
                "Final": "true",
            })

            saved = CRMStore(Path(directory) / "crm.json").snapshot()[0]["transcript"]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["speaker"], "Prospect")
            self.assertEqual(saved[0]["text"], "Can you send the estimate?")

    def test_example_leads_csv_imports_phone_name_and_timezone(self):
        path = Path(__file__).resolve().parents[2] / "Claude outputs" / "example_leads.csv"
        leads, info = parse_csv(path.read_bytes())
        self.assertGreaterEqual(len(leads), 1)
        self.assertEqual(info["skipped"], 0)
        self.assertTrue(leads[0]["phone"].startswith("+"))
        self.assertEqual(leads[0]["timezone"], "Eastern")
        self.assertEqual(leads[0]["name"], "Daniel Edwards")

    def test_local_csv_import_persists_prospects(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            info = crm.add_csv(b"Name,Business Name,Phone Number,Timezone\nAda,Co,(202) 555-0100,Pacific\n")
            self.assertEqual(info["added"], 1)
            saved = CRMStore(Path(directory) / "crm.json").snapshot()[0]
            self.assertEqual(saved["phone"], "+12025550100")
            self.assertEqual(saved["timezone"], "Pacific")

    def test_supabase_csv_import_posts_prospect_rows(self):
        client = FakeSupabaseClient(prospect())
        crm = SupabaseCRMStore(client)
        info = crm.add_csv(b"Name,Phone\nSam,+1 202 555 0199\n")
        self.assertEqual(info["added"], 1)
        self.assertEqual(info["duplicates"], 0)
        imported = next(lead for lead in client.leads.values() if lead["phone"] == "+12025550199")
        self.assertEqual(imported["name"], "Sam")

    def test_supabase_csv_import_is_scoped_to_the_signed_in_user(self):
        client = FakeSupabaseClient(prospect())
        other = SupabaseCRMStore(client, user_id="user-b")
        other.add_csv(b"Name,Phone\nOther,+1 202 555 0101\n")
        mine = SupabaseCRMStore(client, user_id="user-a")
        info = mine.add_csv(b"Name,Phone\nMine,+1 202 555 0102\n")
        self.assertEqual(info["added"], 1)
        phones = [lead["phone"] for lead in mine.snapshot()]
        self.assertEqual(phones, ["+12025550102"])
