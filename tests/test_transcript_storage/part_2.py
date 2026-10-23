import csv
from io import StringIO
from features.prospects import ProspectStore, csv_bytes_for
from tests.test_transcript_storage.fixtures import FakeSupabaseClient
from tests.test_transcript_storage.fixtures import prospect

class Part2:
    def test_snapshot_uses_memory_after_the_first_load(self):
        client = FakeSupabaseClient(prospect())
        client.loads = 0
        original = client.select_all

        def counting(resource, params):
            client.loads += 1
            return original(resource, params)

        client.select_all = counting
        crm = ProspectStore(client=client, user_id="user-a")
        crm.snapshot()
        crm.snapshot()
        self.assertEqual(client.loads, 1)

    def test_csv_columns_follow_the_web_crm_order(self):
        lead = prospect()
        lead["fields"] = {"Email": "a@b.co", "Website": "b.co", "Other Emails": "c@b.co"}
        decoded = csv_bytes_for([lead]).decode("utf-8-sig")
        self.assertEqual(next(csv.reader(StringIO(decoded))), [
            "Prospect", "Company", "State", "City", "Phone Number", "Timezone", "Total Reviews", "Call status",
            "Reviews (Last 30 Days)", "Days Since Last Review", "30-Day %", "Recency Source",
            "Email", "Website", "Other Emails", "scheduled_until", "Call transcript",
        ])

    def test_csv_transcript_field_escapes_multiline_utterances(self):
        lead = prospect()
        lead["transcript"] = [
            {"timestamp": "t1", "speaker": "Agent", "text": 'He said, "yes".'},
            {"timestamp": "t2", "speaker": "Prospect", "text": "Line one\nLine two"},
        ]

        decoded = csv_bytes_for([lead]).decode("utf-8-sig")
        row = next(csv.DictReader(StringIO(decoded)))
        self.assertEqual(
            row["Call transcript"],
            't1 Agent: He said, "yes".\nt2 Prospect: Line one\nLine two',
        )
