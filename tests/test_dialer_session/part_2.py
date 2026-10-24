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
            self.assertEqual(crm.snapshot()[0]["status"], "disqualified")

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
            dialer.update_status(lead["id"], "send_info")
            self.assertEqual(crm.snapshot()[0]["status"], "send_info")
            self.assertIsNone(dialer.pending_outcome)

    def test_every_status_button_ends_the_call_and_sets_the_status_everywhere(self):
        expected = {
            "call": "call_back", "send_info": "send_info", "booked": "booked", "disqualified": "not_interested",
        }
        for status, tag in expected.items():
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                crm = ProspectStore(Path(directory) / "crm.json")
                leads = [{
                    "id": f"prospect-{index}", "name": name, "business": f"Shop {index}",
                    "phone": f"+1202555012{index}", "timezone": "Eastern", "status": "new",
                    "scheduled_until": None, "transcript": [], "fields": {},
                } for index, name in enumerate(("Ada Lovelace", "Grace Hopper"))]
                crm.leads = leads
                dialer = Dialer(crm, str(Path(directory) / ".env"))
                dialer.running = True
                dialer.agent_ready = True
                dialer.session = new_session()
                call = dialer._new_call("prospect", leads[0])
                call["call_uuid"] = "CA-live"
                dialer._pickup(call)
                self.assertIs(dialer.active, call)
                dialer.update_status("prospect-0", status, crm_only=True)
                # The call is hung up on and no longer on the line.
                self.assertTrue(call["cancelled"])
                self.assertIsNone(dialer.active)
                self.assertEqual(dialer.in_flight, {})
                self.assertIsNone(dialer.pending_outcome)
                # The prospect's status is the one the button names, and the call carries its tag.
                shown = {lead["id"]: lead for lead in dialer.leads_catalog()["leads"]}
                self.assertEqual(shown["prospect-0"]["status"], status)
                self.assertEqual(shown["prospect-1"]["status"], "new")
                self.assertEqual(shown["prospect-0"]["call_log"][0]["outcome"], tag)
                self.assertEqual(call["outcome"], tag)
                # The ended call is then logged under that same status, and its tag is kept.
                dialer._call_ended(call, {"CallStatus": "completed", "CallDuration": "12"})
                logged = crm.snapshot()[0]
                self.assertEqual(logged["status"], status)
                self.assertEqual(len(logged["call_log"]), 1)
                self.assertEqual(logged["call_log"][0]["outcome"], tag)
                self.assertEqual(logged["call_log"][0]["duration_seconds"], 12)

    def test_legacy_statuses_read_as_disqualified(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [
                {"id": f"p-{index}", "name": status, "business": status, "phone": f"+1202555010{index}",
                 "timezone": "Eastern", "status": status, "scheduled_until": None, "transcript": [], "fields": {}}
                for index, status in enumerate(("interested", "not_interested", "do_not_call"))
            ]
            self.assertEqual([lead["status"] for lead in crm.snapshot()], ["disqualified"] * 3)

    def test_crm_status_booked_ends_the_call_and_the_queue_moves_on(self):
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
            self.assertEqual(view["in_flight"], [])
            self.assertIsNone(view["pending_outcome"])
            self.assertTrue(view["running"])
            self.assertTrue(call["cancelled"])

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
            self.assertGreater(remaining, timedelta(hours=6) - timedelta(seconds=2))
            self.assertLessEqual(remaining, timedelta(hours=6))
            # The call on the line is already in the dial list, so there is no extra skip entry.
            self.assertEqual([item["id"] for item in kept["call_log"]], [call["token"]])
            view = dialer.public_state()
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
            self.assertTrue(call["cancelled"])
            self.assertIsNone(dialer.active)
            self.assertIsNone(view["pending_outcome"])
            dialer._call_ended(call, {"CallStatus": "completed", "CallDuration": "8"})
            self.assertIsNone(dialer.pending_outcome)

    def test_disqualified_skips_and_keeps_the_prospect_out_of_the_queue_for_good(self):
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
            # The record stays so a re-import finds the number and never adds them back.
            self.assertEqual({lead["id"]: lead["status"] for lead in crm.snapshot()},
                             {"prospect-0": "disqualified", "prospect-1": "new"})
            view = dialer.public_state()
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
            self.assertEqual([lead["id"] for lead in view["pool"]], ["prospect-1"])
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
            self.assertGreater(remaining, timedelta(hours=6) - timedelta(seconds=2))
            self.assertLessEqual(remaining, timedelta(hours=6))
            self.assertEqual(len(crm.snapshot()), 3)

            dialer.pass_next("prospect-1")
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-2")
            dialer.pass_next("prospect-2")
            self.assertIsNone(dialer.public_state()["next_lead"])

            with crm.lock:
                stored = next(lead for lead in crm.leads if lead["id"] == "prospect-0")
                stored["scheduled_until"] = (utc_now() - timedelta(seconds=1)).isoformat()
                for item in stored.get("call_log") or []:
                    item["started_at"] = (utc_now() - timedelta(hours=13)).isoformat()
            returned = next(lead for lead in crm.snapshot() if lead["id"] == "prospect-0")
            self.assertEqual(returned["status"], "new")
            self.assertIsNone(returned["scheduled_until"])
            self.assertEqual(dialer.public_state()["next_lead"]["id"], "prospect-0")

            with crm.lock:
                other = next(lead for lead in crm.leads if lead["id"] == "prospect-1")
                other["status"] = "new"
                other["scheduled_until"] = None
                for item in other.get("call_log") or []:
                    item["started_at"] = (utc_now() - timedelta(hours=13)).isoformat()
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
            self.assertEqual(kept["call_log"][0]["started_at"], (due - timedelta(hours=6)).isoformat())
