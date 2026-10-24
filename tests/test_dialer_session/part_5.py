import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path

from features._dialer import calls
from features._dialer.rules import new_session
from features.dialer import Dialer
from features.prospects import ProspectStore
from shared.infra import utc_now


def _lead(lead_id, phone, name="", status="new", **extra):
    lead = {
        "id": lead_id, "name": name, "business": "", "phone": phone, "timezone": "Eastern",
        "status": status, "scheduled_until": None, "transcript": [], "fields": {},
    }
    lead.update(extra)
    return lead


class Part5:
    def _dialer(self, directory, leads):
        crm = ProspectStore(Path(directory) / "crm.json")
        crm.leads = leads
        dialer = Dialer(crm, str(Path(directory) / ".env"))
        dialer.running = True
        dialer.agent_ready = True
        dialer.session = new_session()
        dialer.callers = ["+15551110001", "+15551110002", "+15551110003"]
        dialer.settings = {"CALLING_START_HOUR": "0", "CALLING_END_HOUR": "24"}
        return crm, dialer

    def _fill_without_twilio(self, dialer):
        launched = []
        original = calls._launch_call
        calls._launch_call = lambda state, call, destination: launched.append((call, destination))
        try:
            dialer.fill_slots()
        finally:
            calls._launch_call = original
        return launched

    def test_closed_prospects_never_go_back_to_new_or_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, _dialer = self._dialer(directory, [
                _lead("booked", "+12025550101", status="booked"),
                _lead("closed", "+12025550102", status="disqualified"),
                _lead("dnc", "+12025550103", status="do_not_call"),
            ])
            for lead_id in ("booked", "closed", "dnc"):
                for status in ("new", "call"):
                    with self.assertRaises(ValueError):
                        crm.set_status(lead_id, status)
            self.assertEqual({lead["id"]: lead["status"] for lead in crm.snapshot()},
                             {"booked": "booked", "closed": "disqualified", "dnc": "disqualified"})
            crm.set_status("booked", "disqualified")
            self.assertEqual(crm.snapshot()[0]["status"], "disqualified")

    def test_closed_prospects_cannot_be_dialed_or_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [
                _lead("booked", "+12025550101", status="booked"),
                _lead("closed", "+12025550102", status="disqualified"),
                _lead("open", "+12025550103"),
            ])
            for lead_id in ("booked", "closed"):
                with self.assertRaises(ValueError):
                    dialer.dial_lead(lead_id)
                dialer.manual_lead_id = lead_id
                self.assertIsNone(calls._claim_manual_lead(dialer, crm.snapshot(), set()))
            self.assertEqual([lead["id"] for lead in calls._pool_leads(dialer)], ["open"])

    def test_another_record_of_a_closed_person_is_never_queued(self):
        with tempfile.TemporaryDirectory() as directory:
            place = {"business": "Pine Pest", "city": "Austin", "state": "TX"}
            crm, dialer = self._dialer(directory, [
                _lead("booked", "+12025550101", "Ada Lovelace", status="booked", **place),
                _lead("same-phone", "(202) 555-0101", "Someone Else"),
                _lead("same-person", "+12025550199", "ada  lovelace", **place),
                _lead("closed", "+12025550102", "Grace Hopper", status="disqualified"),
                _lead("closed-phone", "+12025550102", "Grace H"),
                _lead("interested", "+12025550104", "Alan Turing", status="interested"),
                _lead("interested-phone", "+12025550104", "Alan T"),
                _lead("other-city", "+12025550105", "Ada Lovelace", business="Pine Pest", city="Dallas", state="TX"),
                _lead("open", "+12025550106", "Lin Zhao"),
            ])
            self.assertEqual({lead["id"] for lead in calls._pool_leads(dialer)}, {"other-city", "open"})

    def test_two_records_with_one_phone_are_dialed_once(self):
        with tempfile.TemporaryDirectory() as directory:
            _crm, dialer = self._dialer(directory, [
                _lead("a1", "+12025550101", "Ada"),
                _lead("a2", "(202) 555-0101", "Ada Two"),
                _lead("b", "+12025550102", "Bea"),
                _lead("c", "+12025550103", "Cy"),
            ])
            launched = self._fill_without_twilio(dialer)
            destinations = [calls.twilio.normalize_phone(destination) for _call, destination in launched]
            self.assertEqual(len(destinations), 3)
            self.assertEqual(len(set(destinations)), 3)
            self.assertEqual(sorted(call["lead_id"] for call, _destination in launched), ["a1", "b", "c"])
            self.assertEqual(len({call["caller_id"] for call, _destination in launched}), 3)

    def test_the_same_person_is_not_redialed_by_another_record_right_after_a_dial(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [
                _lead("a1", "+12025550101", "Ada"),
                _lead("a2", "+12025550101", "Ada Two"),
            ])
            launched = self._fill_without_twilio(dialer)
            self.assertEqual([call["lead_id"] for call, _destination in launched], ["a1"])
            call = launched[0][0]
            dialer._call_ended(call, {"CallStatus": "no-answer", "CallDuration": "0"})
            if dialer.advance_timer:
                dialer.advance_timer.cancel()
            self.assertEqual(dialer.in_flight, {})
            self.assertEqual(calls._pool_leads(dialer), [])
            self.assertEqual(self._fill_without_twilio(dialer), [])
            self.assertEqual(crm.snapshot()[1]["status"], "new")

    def test_simultaneous_fills_never_dial_a_lead_twice(self):
        with tempfile.TemporaryDirectory() as directory:
            _crm, dialer = self._dialer(directory, [
                _lead(f"lead-{index}", f"+1202555{index:04d}", f"Lead {index}") for index in range(12)
            ])
            launched = []
            original = calls._launch_call
            calls._launch_call = lambda state, call, destination: launched.append(call["lead_id"])
            try:
                threads = [threading.Thread(target=dialer.fill_slots) for _ in range(8)]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join()
            finally:
                calls._launch_call = original
            self.assertEqual(len(launched), 3)
            self.assertEqual(len(set(launched)), 3)

    def test_a_dropped_line_never_shortens_a_manual_callback(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [_lead("held", "+12025550101", "Ada")])
            manual = crm.set_status("held", "call")
            from features._dialer import queue
            self.assertIsNone(queue.schedule_dropped_callback(dialer, "held"))
            self.assertEqual(crm.snapshot()[0]["scheduled_until"], manual["scheduled_until"])

    def test_a_manual_callback_is_six_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [
                _lead("menu", "+12025550101", "Ada"),
                _lead("live", "+12025550102", "Grace"),
            ])

            def remaining(lead_id):
                lead = next(item for item in crm.snapshot() if item["id"] == lead_id)
                self.assertEqual(lead["status"], "call")
                return datetime.fromisoformat(lead["scheduled_until"]) - utc_now()

            dialer.update_status("menu", "call")
            self.assertGreater(remaining("menu"), timedelta(hours=6) - timedelta(seconds=5))
            self.assertLessEqual(remaining("menu"), timedelta(hours=6))

            call = dialer._new_call("prospect", crm.snapshot()[1])
            call["picked_up"] = True
            dialer.active = call
            dialer.update_status("live", disposition="callback")
            self.assertGreater(remaining("live"), timedelta(hours=6) - timedelta(seconds=5))
            self.assertLessEqual(remaining("live"), timedelta(hours=6))
            # The call is already in the dial list, so a callback adds no skipped record.
            dialer.public_state()
            log = next(item for item in crm.snapshot() if item["id"] == "live")["call_log"]
            self.assertNotIn("skipped", [item["answered_by"] for item in log])

    def test_booking_from_the_crm_is_counted_once_in_metrics_and_the_session(self):
        from features.metrics import MetricsStore
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [_lead("a", "+12025550101", "Ada"), _lead("b", "+12025550102", "Grace")])
            dialer.metrics = MetricsStore(Path(directory) / "metrics.json")
            dialer.update_status("a", "booked", crm_only=True)
            dialer.update_status("a", "booked", crm_only=True)
            dialer.update_status("b", "booked")
            self.assertEqual(dialer.metrics.snapshot()["all_time"]["booked"], 2)
            self.assertEqual(dialer.metrics.snapshot()["today"]["booked"], 2)
            self.assertEqual(dialer.session["meetings_booked"], 2)

    def test_transcript_lines_from_a_second_twilio_session_are_kept(self):
        with tempfile.TemporaryDirectory() as directory:
            crm, dialer = self._dialer(directory, [_lead("a", "+12025550101", "Ada")])
            call = dialer._new_call("prospect", crm.snapshot()[0])
            call["call_uuid"] = "CA1"
            call["picked_up"] = True
            dialer.active = call

            def final(session, sequence, text):
                dialer.handle_webhook(call["token"], "transcript", {
                    "TranscriptionEvent": "transcription-content", "TranscriptionSid": session,
                    "Track": "inbound_track", "SequenceId": sequence, "Final": "true",
                    "TranscriptionData": '{"transcript": "%s"}' % text,
                })

            final("GT1", "1", "First session words.")
            final("GT2", "1", "Second session words.")
            final("GT2", "1", "Second session words.")
            texts = [item["text"] for item in crm.snapshot()[0]["transcript"]]
            self.assertEqual(texts, ["First session words.", "Second session words."])
