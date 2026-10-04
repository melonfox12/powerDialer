import threading
from twilio.jwt.access_token import AccessToken
from twilio.jwt.access_token.grants import VoiceGrant
from twilio_calls.client import escape_xml

class VoiceMixin:
    def _watch_token(self, token):
        index = self.token_index
        if index is not None:
            index.register(token, self)

    def _release_tokens(self):
        index = self.token_index
        if index is None:
            return
        for token in list(self.calls):
            index.forget(token)

    def voice_access_token(self):
        self.record_activity("Requesting browser Voice access token", "api")
        values = self._values()
        required = (
            "TWILIO_ACCOUNT_SID", "TWILIO_API_KEY", "TWILIO_API_SECRET",
            "TWILIO_TWIML_APP_SID",
        )
        missing = [key for key in required if not values.get(key)]
        if missing:
            raise ValueError("Complete Twilio Account SID, API Key SID, API Key Secret, and TwiML App SID in Settings.")
        token = AccessToken(
            values["TWILIO_ACCOUNT_SID"],
            values["TWILIO_API_KEY"],
            values["TWILIO_API_SECRET"],
            identity="prospect_desk_agent",
            ttl=3600,
        )
        token.add_grant(VoiceGrant(outgoing_application_sid=values["TWILIO_TWIML_APP_SID"]))
        return token.to_jwt()

    def handle_client_voice(self, params):
        token = params.get("CallToken", "")
        with self.lock:
            call = self.calls.get(token)
            if not call or call["kind"] != "agent" or call["cancelled"] or not self.running:
                return 200, "application/xml", "<Response><Hangup/></Response>"
            call_uuid = params.get("CallSid", "")
            if call_uuid:
                call["call_uuid"] = call_uuid
                self.agent_call_uuid = call_uuid
            self.agent_ready = True
            self.last_event = "Computer audio connected"
        self.record_activity("Browser audio joined the conference", "call")
        threading.Thread(target=self.fill_slots, daemon=True).start()
        xml = (
            f'<Response><Dial action="{escape_xml(self._url(call, "agent-ended"))}" method="POST">'
            '<Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="true">'
            f'{escape_xml(self.conference)}</Conference></Dial></Response>'
        )
        return 200, "application/xml", xml
