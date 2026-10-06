import tempfile
from pathlib import Path
from features.prospects import ProspectStore
from twilio_calls import TwilioDialer

class Part4:
    def test_caller_ids_rotate_and_only_one_prospect_is_dialed(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
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

    def test_manual_dial_calls_the_chosen_prospect_and_can_wait_for_the_line(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            auto = {
                "id": "auto", "name": "Auto", "business": "Shop",
                "phone": "+12025550100", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            chosen = {
                "id": "chosen", "name": "Chosen", "business": "Studio",
                "phone": "+12025550199", "timezone": "Unknown", "status": "interested",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            blocked = {
                "id": "blocked", "name": "Blocked", "business": "No",
                "phone": "+12025550188", "timezone": "Eastern", "status": "do_not_call",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [auto, chosen, blocked]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            dialer._launch_call = lambda call, destination: launched.append((destination, call["lead_id"]))

            with self.assertRaises(ValueError):
                dialer.dial_lead(blocked["id"])
            with self.assertRaises(KeyError):
                dialer.dial_lead("missing")

            dialer.fill_slots()
            self.assertEqual(launched, [(auto["phone"], auto["id"])])

            queued = dialer.dial_lead(chosen["id"])
            self.assertEqual(queued["dial_status"], "next")
            self.assertEqual(queued["next_lead"]["id"], chosen["id"])
            self.assertEqual(dialer.manual_lead_id, chosen["id"])
            self.assertEqual(len(launched), 1)

            dialer.in_flight.clear()
            dialer.fill_slots()
            self.assertEqual(launched[-1], (chosen["phone"], chosen["id"]))
            self.assertIsNone(dialer.manual_lead_id)

            again = dialer.dial_lead(chosen["id"])
            self.assertEqual(again["dial_status"], "already")
            self.assertEqual(len(launched), 2)

            dialer.manual_lead_id = auto["id"]
            dialer.stop()
            self.assertIsNone(dialer.manual_lead_id)

    def test_manual_dial_resumes_an_idle_paused_session(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            chosen = {
                "id": "chosen", "name": "Chosen", "business": "Studio",
                "phone": "+12025550199", "timezone": "Unknown", "status": "call",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [chosen]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.paused = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "8", "CALLING_END_HOUR": "9"}
            launched = []
            dialer._launch_call = lambda call, destination: launched.append(destination)

            state = dialer.dial_lead(chosen["id"])

            self.assertFalse(dialer.paused)
            self.assertEqual(state["dial_status"], "now")
            self.assertEqual(launched, [chosen["phone"]])
