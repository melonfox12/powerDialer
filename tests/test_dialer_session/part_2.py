import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from features.prospects import ProspectStore
from features._dialer.rules import new_session
from features.dialer import Dialer
from shared.infra import utc_now

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
            self.assertIsNone(dialer.pending_outcome)
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            dialer.pending_outcome = lead["id"]
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
            dialer.update_status("prospect-0", "booked", crm_only=True)
            view = dialer.public_state()
            self.assertEqual(crm.snapshot()[0]["status"], "booked")
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
            self.assertEqual(view["in_flight"][0]["lead_id"], "prospect-0")
            self.assertIsNone(view["pending_outcome"])
            self.assertTrue(view["running"])
            self.assertFalse(call["cancelled"])

    def test_callback_skips_and_starts_the_timer(self):
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
            call["picked_up"] = True
            dialer.update_status("prospect-0", "call", crm_only=True)
            kept = next(lead for lead in crm.snapshot() if lead["id"] == "prospect-0")
            due = datetime.fromisoformat(kept["scheduled_until"])
            remaining = due - utc_now()
            self.assertEqual(kept["status"], "call")
            self.assertGreater(remaining, timedelta(hours=12) - timedelta(seconds=2))
            self.assertLessEqual(remaining, timedelta(hours=12))
            self.assertEqual(kept["call_log"][0]["answered_by"], "skipped")
            view = dialer.public_state()
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
            self.assertTrue(call["skip_closed"])
            self.assertIsNone(dialer.active)
            self.assertIsNone(view["pending_outcome"])
            dialer._call_ended(call, {"CallStatus": "completed", "CallDuration": "8"})
            self.assertIsNone(dialer.pending_outcome)

    def test_disqualified_skips_and_deletes_the_prospect(self):
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
            dialer.session = new_session()
            call = dialer._new_call("prospect", leads[0])
            dialer.update_status("prospect-0", "disqualified", crm_only=True)
            self.assertEqual([lead["id"] for lead in crm.snapshot()], ["prospect-1"])
            view = dialer.public_state()
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
            self.assertEqual(view["in_flight"], [])
            self.assertTrue(call["cancelled"])
            self.assertTrue(call["skip_closed"])
            self.assertIsNone(view["pending_outcome"])

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
            self.assertEqual(kept["status"], "call")
            self.assertEqual(kept["call_log"][0]["answered_by"], "skipped")
            skipped_at = datetime.fromisoformat(kept["call_log"][0]["started_at"])
            self.assertLessEqual(abs(utc_now() - skipped_at), timedelta(seconds=2))
            due = datetime.fromisoformat(kept["scheduled_until"])
            remaining = due - utc_now()
            self.assertGreater(remaining, timedelta(hours=12) - timedelta(seconds=2))
            self.assertLessEqual(remaining, timedelta(hours=12))
            self.assertEqual(len(crm.snapshot()), 3)

            dialer.pass_next("prospect-1")
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-2")
            dialer.pass_next("prospect-2")
            self.assertIsNone(dialer.public_state()["next_lead"])

            with crm.lock:
                stored = next(lead for lead in crm.leads if lead["id"] == "prospect-0")
                stored["scheduled_until"] = (utc_now() - timedelta(seconds=1)).isoformat()
            returned = next(lead for lead in crm.snapshot() if lead["id"] == "prospect-0")
            self.assertEqual(returned["status"], "new")
            self.assertIsNone(returned["scheduled_until"])
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-0")

            with crm.lock:
                other = next(lead for lead in crm.leads if lead["id"] == "prospect-1")
                other["status"] = "new"
                other["scheduled_until"] = None
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

    def test_open_callback_without_a_call_is_listed_as_a_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            due = utc_now().replace(microsecond=0) + timedelta(hours=6)
            crm.leads = [{
                "id": "prospect-0",
                "name": "Ada Lovelace",
                "business": "Shop 0",
                "phone": "+12025550120",
                "timezone": "Eastern",
                "status": "call",
                "scheduled_until": due.isoformat(),
                "transcript": [],
                "fields": {},
            }]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.public_state()
            kept = crm.snapshot()[0]
            self.assertEqual(kept["call_log"][0]["answered_by"], "skipped")
            self.assertEqual(kept["call_log"][0]["started_at"], (due - timedelta(hours=12)).isoformat())
