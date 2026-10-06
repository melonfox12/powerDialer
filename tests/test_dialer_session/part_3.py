import tempfile
from pathlib import Path
from features.prospects import ProspectStore
from core.dialer_session import new_session
from twilio_calls import TwilioDialer

class Part3:
    def test_answer_bridges_any_pickup_and_keeps_voicemail_on_the_line(self):
        with tempfile.TemporaryDirectory() as directory:
            crm = ProspectStore(Path(directory) / "crm.json")
            lead = {
                "id": "prospect-1", "name": "Onyx", "business": "Onyx",
                "phone": "+12025550123", "timezone": "Eastern", "status": "new",
                "scheduled_until": None, "transcript": [], "fields": {},
            }
            crm.leads = [lead]
            dialer = TwilioDialer(crm, str(Path(directory) / ".env"))
            dialer.public_base_url = "https://example.test"
            dialer.conference = "crm-test"
            dialer.save_settings({"session_goal": 20})
            dialer.running = True
            dialer.session = new_session()
            call = dialer._new_call("prospect", lead)
            call["call_uuid"] = "CA-test"
            call["caller_id"] = "+15551230001"

            status, _, twiml = dialer.handle_webhook(call["token"], "answer", {"CallSid": "CA-test"})
            self.assertEqual(status, 200)
            self.assertIn("<Transcription", twiml)
            self.assertIn("<Conference", twiml)
            self.assertNotIn("<Pause", twiml)
            self.assertNotIn("Please hold", twiml)
            self.assertEqual(call["state"], "live")
            self.assertIs(dialer.active, call)
            self.assertEqual(dialer.public_state()["live_transcript"]["lead_id"], lead["id"])
            self.assertEqual(dialer.public_state()["current_caller_id"], "+15551230001")

            hung = []
            dialer._hangup_call = lambda call_uuid: hung.append(call_uuid)
            dialer._machine_result(call, {"AnsweredBy": "machine_end_beep"})
            self.assertEqual(hung, [])
            self.assertEqual(call["answered_by"], "voicemail")
            self.assertIs(dialer.active, call)
            self.assertEqual(crm.snapshot()[0]["status"], "new")
            self.assertEqual(dialer.session["connects"], 1)
