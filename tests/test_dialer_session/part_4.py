import tempfile
from datetime import datetime, timedelta
import zlib
from pathlib import Path
from features._dialer import calls
from features._dialer import twilio
from features._dialer.rules import new_session
from features._dialer.twilio import TwilioError
from features.dialer import Dialer
from features.prospects import ProspectStore
from shared.infra import utc_now
from shared.vocabulary import NO_PICKUP_CALLBACK_HOURS

class Part4:
    def test_fill_slots_waits_until_the_parallel_wave_finishes(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [
                {
                    "id": f"prospect-{index}",
                    "name": f"Prospect {index}",
                    "business": "Shop",
                    "phone": f"+1202555012{index}",
                    "timezone": "Eastern",
                    "status": "new",
                    "scheduled_until": None,
                    "transcript": [],
                    "fields": {},
                }
                for index in range(5)
            ]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            dialer.fill_slots()
            self.assertEqual(len(launched), 3)
            dialer.fill_slots()
            self.assertEqual(len(launched), 3)
            dialer.in_flight.pop(next(iter(dialer.in_flight)))
            dialer.fill_slots()
            self.assertEqual(len(launched), 3)

    def test_three_lines_dial_at_once_and_caller_ids_rotate(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            leads = []
            for index in range(6):
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
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append((call["caller_id"], destination))
            try:
                self._rotate_callers(dialer, launched)
            finally:
                calls._launch_call = original_launch

    def _rotate_callers(self, dialer, launched):
            dialer.fill_slots()
            dialer.fill_slots()
            self.assertEqual(
                [caller for caller, _destination in launched],
                ["+15551110001", "+15551110002", "+15551110003"],
            )
            self.assertEqual(len({destination for _caller, destination in launched}), 3)

            dialer.in_flight.clear()
            dialer.active = None
            dialer.fill_slots()
            self.assertEqual(
                [caller for caller, _destination in launched],
                [
                    "+15551110001", "+15551110002", "+15551110003",
                    "+15551110001", "+15551110002", "+15551110003",
                ],
            )

    def test_first_answer_connects_and_the_other_lines_go_back_in_the_queue(self):
        from features._dialer._call_events import pickup
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            leads = []
            for index in range(3):
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
                    "city": "Hartford",
                    "state": "CT",
                    "review_count": 10 + index,
                })
            crm.leads = leads
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.session = new_session()
            dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(call)
            try:
                dialer.fill_slots()
                self.assertEqual(len(launched), 3)
                self.assertTrue(pickup._pickup(dialer, launched[0]))
                self.assertFalse(pickup._pickup(dialer, launched[1]))
            finally:
                calls._launch_call = original_launch
            self.assertIs(dialer.active, launched[0])
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            for lead in crm.snapshot()[1:]:
                self.assertEqual(lead["status"], "call")
                remaining = datetime.fromisoformat(lead["scheduled_until"]) - utc_now()
                self.assertGreater(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS) - timedelta(seconds=5))
                self.assertLessEqual(remaining, timedelta(hours=NO_PICKUP_CALLBACK_HOURS))
                self.assertEqual([item["answered_by"] for item in lead["call_log"]], ["race_lost"])
            dialer.public_state()
            for lead in crm.snapshot()[1:]:
                self.assertEqual([item["answered_by"] for item in lead["call_log"]], ["race_lost"])
            self.assertTrue(launched[1]["skip_closed"])
            self.assertTrue(launched[2]["skip_closed"])
            self.assertFalse(launched[0]["cancelled"])

    def test_metrics_save_failure_still_places_the_call(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [{
                "id": "prospect-0", "name": "Ada", "business": "Shop",
                "phone": "+12025550100", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.session = new_session()

            class BrokenMetrics:
                def bump(self, key, amount=1):
                    raise OSError("missing increment_metric")

                def save_session(self, session):
                    raise OSError("missing session save")

            dialer.metrics = BrokenMetrics()
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(destination)
            try:
                dialer.fill_slots()
            finally:
                calls._launch_call = original_launch
            self.assertEqual(launched, ["+12025550100"])

    def test_skip_still_dials_when_metrics_cannot_be_saved(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = [{
                "id": "prospect-0", "name": "Ada", "business": "Shop",
                "phone": "+12025550100", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }, {
                "id": "prospect-1", "name": "Grace", "business": "Lab",
                "phone": "+12025550101", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.session = new_session()

            class BrokenMetrics:
                def bump(self, key, amount=1):
                    raise OSError("missing increment_metric")

                def save_session(self, session):
                    raise OSError("missing session save")

            dialer.metrics = BrokenMetrics()
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(destination)
            try:
                view = dialer.pass_next("prospect-0")
            finally:
                calls._launch_call = original_launch
            self.assertEqual(launched, ["+12025550101"])
            self.assertIsNone(view["next_lead"])
            skipped = next(lead for lead in crm.snapshot() if lead["id"] == "prospect-0")
            self.assertEqual(skipped["status"], "call")

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
                "phone": "+12025550199", "timezone": "Unknown", "status": "send_info",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            blocked = {
                "id": "blocked", "name": "Blocked", "business": "No",
                "phone": "+12025550188", "timezone": "Eastern", "status": "do_not_call",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [auto, chosen, blocked]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append((destination, call["lead_id"]))
            try:
                self._manual_dial(dialer, launched, auto, chosen, blocked)
            finally:
                calls._launch_call = original_launch

    def _manual_dial(self, dialer, launched, auto, chosen, blocked):
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
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.paused = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "8", "CALLING_END_HOUR": "9"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(destination)
            try:
                state = dialer.dial_lead(chosen["id"])
            finally:
                calls._launch_call = original_launch

            self.assertFalse(dialer.paused)
            self.assertEqual(state["dial_status"], "now")
            self.assertEqual(launched, [chosen["phone"]])

    def test_auto_dial_calls_the_prospect_left_after_a_skip(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            first = {
                "id": "first", "name": "Ada Lovelace", "business": "Shop",
                "phone": "+12025550100", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            second = {
                "id": "second", "name": "Grace Hopper", "business": "Lab",
                "phone": "+12025550101", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [first, second]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.pass_next(first["id"])
            dialer.running = True
            dialer.agent_ready = True
            dialer.callers = ["+15551110001"]
            dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
            launched = []
            original_launch = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append((destination, call["lead_id"]))
            try:
                dialer.fill_slots()
            finally:
                calls._launch_call = original_launch
            self.assertEqual(launched, [(second["phone"], second["id"])])
            self.assertEqual(len(crm.snapshot()), 2)

    def test_one_bad_number_waits_and_an_auth_failure_pauses(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            first = {
                "id": "first", "name": "Ada", "business": "Shop",
                "phone": "+12025550100", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            second = {
                "id": "second", "name": "Grace", "business": "Lab",
                "phone": "+12025550101", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [first, second]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.callers = ["+15551110001", "+15551110002"]
            dialer.settings = {
                "TWILIO_ACCOUNT_SID": "ACexample",
                "TWILIO_AUTH_TOKEN": "token",
                "AUTO_ADVANCE_DELAY_SECONDS": "3",
            }
            bad = dialer._new_call("prospect", first)
            other = dialer._new_call("prospect", second)
            original = twilio.twilio_request
            twilio.twilio_request = lambda *args, **kwargs: (_ for _ in ()).throw(
                TwilioError("Twilio error 21211: Invalid 'To' Phone Number")
            )
            try:
                calls._create_call(dialer, bad, first["phone"])
                self.assertFalse(dialer.paused)
                self.assertEqual(dialer.last_error, "")
                self.assertNotIn(bad["token"], dialer.in_flight)
                self.assertIn(other["token"], dialer.in_flight)
                self.assertIsNotNone(dialer.advance_timer)
                dialer.advance_timer.cancel()
                twilio.twilio_request = lambda *args, **kwargs: (_ for _ in ()).throw(
                    TwilioError("Twilio error 401: authentication failed")
                )
                calls._create_call(dialer, other, second["phone"])
            finally:
                twilio.twilio_request = original
                if dialer.advance_timer:
                    dialer.advance_timer.cancel()
            self.assertTrue(dialer.paused)
            self.assertIn("401", dialer.last_error)

    def test_a_prospect_dialed_in_the_last_forty_eight_hours_stays_out_of_the_queue(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            recent = {
                "id": "recent", "name": "Recent", "business": "Shop",
                "phone": "+12025550101", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
                "call_log": [{
                    "id": "CA-recent",
                    "started_at": utc_now().isoformat(),
                    "ended_at": "",
                    "answered_by": "no_answer",
                }],
            }
            older = {
                "id": "older", "name": "Older", "business": "Shop",
                "phone": "+12025550102", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
                "call_log": [{
                    "id": "CA-older",
                    "started_at": (utc_now() - timedelta(hours=49)).isoformat(),
                    "ended_at": "",
                    "answered_by": "no_answer",
                }],
            }
            fresh = {
                "id": "fresh", "name": "Fresh", "business": "Shop",
                "phone": "+12025550103", "timezone": "Pacific", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [recent, older, fresh]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.session = new_session()
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["older", "fresh"])

            dialer.set_timezone_filter("Eastern")
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["older"])
            dialer.set_timezone_filter("Pacific")
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["fresh"])
            dialer.set_timezone_filter("")
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["older", "fresh"])
            self.assertEqual(
                [group["name"] for group in dialer.public_state()["timezone_groups"]],
                ["Eastern", "Pacific"],
            )
            self.assertEqual(dialer.public_state()["timezone_groups"][0]["count"], 1)

    def test_send_info_pool_mode_only_dials_send_info_prospects(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            new_lead = {
                "id": "new-1", "name": "New", "business": "Shop",
                "phone": "+12025550101", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            send_info = {
                "id": "info-1", "name": "Info", "business": "Shop",
                "phone": "+12025550102", "timezone": "Eastern", "status": "send_info",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [new_lead, send_info]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.session = new_session()
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["new-1"])
            dialer.set_pool_filters(pool_status="send_info")
            self.assertEqual(dialer.public_state()["dial_pool_status"], "send_info")
            self.assertEqual([lead["id"] for lead in dialer.public_state()["pool"]], ["info-1"])

    def test_a_line_with_no_twilio_update_is_released(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Ada", "business": "Shop",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = Dialer(crm, str(Path(directory) / ".env"))
            dialer.running = True
            dialer.agent_ready = True
            dialer.session = new_session()
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-silent"
            original = twilio._hangup_call
            twilio._hangup_call = lambda *_args: None
            try:
                calls._expire_silent_call(dialer, call["token"])
                self.assertTrue(call["end_processed"])
                self.assertNotIn(call["token"], dialer.in_flight)
                kept = crm.snapshot()[0]
                self.assertEqual(kept["status"], "call")
                self.assertTrue(kept["scheduled_until"])
                call["end_processed"] = False
                call["picked_up"] = True
                dialer.in_flight[call["token"]] = call
                calls._expire_silent_call(dialer, call["token"])
                self.assertFalse(call["end_processed"])
                self.assertIn(call["token"], dialer.in_flight)
            finally:
                twilio._hangup_call = original
                if dialer.advance_timer:
                    dialer.advance_timer.cancel()

    def test_scan_crm_copies_an_open_callback_onto_a_reimported_prospect(self):
        now = utc_now().replace(microsecond=0)
        due = now + timedelta(hours=1)
        later = now + timedelta(hours=1, minutes=30)
        leads = [
            self._scan_lead("held", "Ada Lovelace", "call", due, city="Austin", state="TX", dialed=True),
            self._scan_lead("held-later", "Ada Lovelace", "call", later, city="Austin", state="TX", dialed=True),
            self._scan_lead("fresh", "ada   lovelace", "new", None, fields={"City": "Austin", "State": "tx"}),
            self._scan_lead("other-city", "Ada Lovelace", "new", None, city="Dallas", state="TX"),
            self._scan_lead("booked", "Ada Lovelace", "booked", None, city="Austin", state="TX"),
            self._scan_lead("far", "Grace Hopper", "call", now + timedelta(hours=50), city="Austin", state="TX", dialed=True),
            self._scan_lead("far-copy", "Grace Hopper", "new", None, city="Austin", state="TX"),
            self._scan_lead("quiet", "Alan Turing", "call", due, city="Austin", state="TX"),
            self._scan_lead("quiet-copy", "Alan Turing", "new", None, city="Austin", state="TX"),
            self._scan_lead("blank", "", "new", None, city="Austin", state="TX"),
            self._scan_lead("zone", "Lin Zhao", "call", due, timezone="Pacific", dialed=True),
            self._scan_lead("zone-copy", "Lin Zhao", "new", None, timezone="Pacific"),
            self._scan_lead("zone-other", "Lin Zhao", "new", None, timezone="Eastern"),
        ]
        plan = {item["id"]: item["scheduled_until"] for item in calls.callback_sync_plan(leads, now)}
        self.assertEqual(set(plan), {"fresh", "zone-copy"})
        self.assertEqual(plan["fresh"], later.isoformat())
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            crm.leads = leads
            result = Dialer(crm, str(Path(directory) / ".env")).scan_crm()
            stored = {lead["id"]: lead for lead in crm.snapshot()}
            self.assertEqual(result["synced"], 2)
            self.assertEqual(stored["fresh"]["status"], "call")
            self.assertEqual(stored["fresh"]["scheduled_until"], later.isoformat())
            self.assertEqual(stored["held"]["status"], "call")
            self.assertEqual(stored["held"]["scheduled_until"], due.isoformat())
            self.assertEqual(stored["other-city"]["status"], "new")
            self.assertEqual(stored["far-copy"]["status"], "new")
            self.assertEqual(stored["quiet-copy"]["status"], "new")
            self.assertEqual(stored["zone-other"]["status"], "new")
            self.assertEqual(stored["booked"]["status"], "booked")
            pool_ids = {lead["id"] for lead in result["state"]["pool"]}
            self.assertNotIn("fresh", pool_ids)
            self.assertIn("other-city", pool_ids)

    def _scan_lead(self, lead_id, name, status, due, city="", state="", timezone="Central", fields=None, dialed=False):
        return {
            "id": lead_id,
            "name": name,
            "business": "Shop",
            "phone": f"+1202555{zlib.crc32(lead_id.encode()) % 10000:04d}",
            "timezone": timezone,
            "status": status,
            "scheduled_until": due.isoformat() if due else None,
            "city": city,
            "state": state,
            "transcript": [],
            "fields": {**(fields or {}), "callback_timer_48h_to_2h": True},
            "call_log": [{"id": f"dial-{lead_id}", "started_at": utc_now().isoformat()}] if dialed else [],
        }
