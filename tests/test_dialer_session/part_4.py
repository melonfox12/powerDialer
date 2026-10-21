import tempfile
from pathlib import Path
from features._dialer import calls
from features._dialer import twilio
from features._dialer.rules import new_session
from features._dialer.twilio import TwilioError
from features.dialer import Dialer
from features.prospects import ProspectStore

class Part4:
    def test_three_lines_dial_at_once_and_caller_ids_rotate(self):
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

    def test_first_answer_connects_and_the_other_lines_become_callbacks(self):
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
                self.assertTrue(lead.get("scheduled_until"))
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
            self.assertEqual(view["next_lead"]["id"], "prospect-1")
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
                "phone": "+12025550199", "timezone": "Unknown", "status": "interested",
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
