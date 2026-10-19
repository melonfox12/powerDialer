import tempfile
from pathlib import Path
from features.prospects import ProspectStore
from features._dialer.rules import new_session
from features.dialer import Dialer

class Part2:
    def test_callback_is_persisted_and_do_not_call_leaves_the_auto_dial_pool(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1",
                "name": "Onyx Garage Floors",
                "business": "Onyx Garage Floors",
                "phone": "+12025550123",
                "timezone": "Eastern",
                "status": "new",
                "scheduled_until": None,
                "transcript": [],
                "fields": {},
            }
            crm.leads = [lead]
            callback = crm.set_status("prospect-1", "call", "2030-01-02T14:00:00+00:00")
            self.assertEqual(callback["scheduled_until"], "2030-01-02T14:00:00+00:00")
            crm.set_status("prospect-1", "do_not_call")
            self.assertEqual(crm.timezone_groups(), [])
            self.assertEqual(crm.snapshot()[0]["status"], "do_not_call")

    def test_any_pickup_connects_and_a_long_live_call_counts_as_a_conversation(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.session = new_session(goal=1)
            dialer.settings = {"CONVERSATION_THRESHOLD_SECONDS": "30"}
            call = dialer._new_call("prospect", lead)
            dialer._pickup(call)
            self.assertEqual(dialer.session["connects"], 1)
            dialer._machine_result(call, {"AnsweredBy": "human"})
            self.assertEqual(dialer.session["connects"], 1)
            self.assertEqual(call["answered_by"], "human")
            dialer._call_ended(call, {"CallDuration": "30"})
            self.assertEqual(dialer.session["conversations"], 1)
            self.assertEqual(dialer.pending_outcome, lead["id"])
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            dialer.choose_outcome(lead["id"], "interested")
            self.assertEqual(crm.snapshot()[0]["status"], "interested")

    def test_crm_status_keeps_the_call_and_the_queue_head(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            leads = []
            for index, name in enumerate(("Ada Lovelace", "Grace Hopper")):
                leads.append({
                    "id": f"prospect-{index}",
                    "name": name,
                    "business": f"Shop {index}",
                    "phone": f"+1202555012{index}",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                })
            crm.leads = leads
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.session = new_session()
            call = dialer._new_call("prospect", leads[0])
            dialer.update_status("prospect-0", "disqualified", crm_only=True)
            view = dialer.public_state()
            self.assertEqual(crm.snapshot()[0]["status"], "disqualified")
            self.assertEqual(view["next_lead"]["id"], "prospect-0")
            self.assertEqual(view["in_flight"][0]["lead_id"], "prospect-0")
            self.assertIsNone(view["pending_outcome"])
            self.assertTrue(view["running"])
            self.assertFalse(call["cancelled"])

    def test_skip_keeps_the_prospect_and_shows_the_following_one(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            leads = []
            for index, name in enumerate(("Ada Lovelace", "Grace Hopper", "Katherine Johnson")):
                leads.append({
                    "id": f"prospect-{index}",
                    "name": name,
                    "business": f"Shop {index}",
                    "phone": f"+1202555012{index}",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                })
            crm.leads = leads
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            self.assertFalse(dialer.running)
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-0")

            skipped = dialer.pass_next("prospect-0")
            self.assertEqual(skipped["next_lead"]["id"], "prospect-1")
            kept = next(lead for lead in crm.snapshot() if lead["id"] == "prospect-0")
            self.assertEqual(kept["status"], "new")
            self.assertTrue(kept["passed_at"])
            self.assertEqual(len(crm.snapshot()), 3)

            dialer.pass_next("prospect-1")
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-2")
            dialer.pass_next("prospect-2")
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-0")

            dialer.running = True
            dialer.in_flight["token"] = {"lead_id": "prospect-0", "kind": "prospect"}
            skipped_live = dialer.pass_next("prospect-0")
            self.assertEqual(skipped_live["next_lead"]["id"], "prospect-1")
            self.assertEqual(dialer.in_flight, {})
            self.assertIsNone(dialer.active)
            dialer.running = False
            crm.remove("prospect-0")
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-1")
            self.assertEqual(len(crm.snapshot()), 2)
