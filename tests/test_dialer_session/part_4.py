import tempfile
from pathlib import Path
from crm_store import CRMStore
from twilio_calls import TwilioDialer

class Part4:
    def test_caller_ids_rotate_and_only_one_prospect_is_dialed(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = CRMStore(Path(directory) / "crm.json")
            leads = []
            for index in range(4):
                leads.append({
                    "id": f"prospect-{index}",
                    "name": f"Prospect {index}",
                    "business": "Shop",
                    "phone": f"+1202555012{index}",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                })
            crm.leads = leads
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            dialer._launch_call = lambda call, destination: launched.append((call["caller_id"], destination))

            dialer.fill_slots()
            dialer.fill_slots()
            self.assertEqual(len(launched), 1)
            self.assertEqual(launched[0][0], "+15551110001")

            dialer.in_flight.clear()
            dialer.active = None
            dialer.fill_slots()
            dialer.in_flight.clear()
            dialer.fill_slots()
            dialer.in_flight.clear()
            dialer.fill_slots()
            self.assertEqual(
                [caller for caller, _destination in launched],
                ["+15551110001", "+15551110002", "+15551110003", "+15551110001"],
            )
