"""Webhook and browser-voice dispatch. Imports pickup, transcript, then ended."""

import threading

from features._dialer._call_events import ended, pickup, transcript
from features import ai_voice_runtime
from features._dialer import queue, slots, voice_session
from features._dialer import projection, rules, twilio
from features._dialer.twilio import escape_xml
from shared.vocabulary import OUTCOME_METRIC

def _uuid(params):
    return params.get("CallSid") or params.get("call_uuid") or ""

def handle_webhook(state, token, action, params):
    with state.lock:
        call = state.calls.get(token)
        if not call:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        call_uuid = _uuid(params)
        if call_uuid:
            call["call_uuid"] = call_uuid
            if call["kind"] == "agent":
                state.agent_call_uuid = call_uuid
        state.record_activity(f"Call callback: {action}", "webhook")
    if action == "status":
        call_status = params.get("CallStatus", "").lower()
        if call_status == "ringing":
            action = "ring"
        elif call_status in ("completed", "busy", "failed", "no-answer", "canceled"):
            action = "hangup"
        else:
            return 200, "text/plain", "OK"
    if action == "ring":
        with state.lock:
            if (
                call["kind"] == "prospect"
                and not call["handled"]
                and not call["cancelled"]
                and not call.get("picked_up")
            ):
                call["state"] = "ringing"
        if call.get("cancelled") and call_uuid:
            twilio._hangup_call(state, call_uuid)
        return 200, "text/plain", "OK"
    if action == "answer" and call["kind"] == "agent":
        if not voice_session.uses_browser_agent_leg(state):
            return 200, "application/xml", "<Response><Hangup/></Response>"
        with state.lock:
            state.agent_ready = True
            state.last_event = "Computer audio connected"
        threading.Thread(target=slots.fill_slots, args=(state,), daemon=True).start()
        xml = ("<Response><Say>Dialer connected. Stay on the line.</Say><Dial>"
               '<Conference beep="false" startConferenceOnEnter="true" '
               f'endConferenceOnExit="false">{escape_xml(state.conference)}</Conference></Dial></Response>')
        return 200, "application/xml", xml
    if action == "answer":
        if call["kind"] != "prospect" or call["cancelled"] or not state.running:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        with state.lock:
            rules.clear_stale_active(state)
            lost = call.get("skip_closed") or (state.active is not None and state.active is not call)
            joined = call.get("picked_up") and state.active is call
        if lost:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        if joined:
            if voice_session.is_ai_voice(state):
                if not call.get("bridge_session_id"):
                    ai_voice_runtime.start_call_session(state, call)
                if not ai_voice_runtime.voice_configured(state.read_settings()):
                    transcript.schedule_live_transcription(state, call)
                return 200, "application/xml", ai_voice_runtime.ai_stream_twiml(state, call)
            transcript.schedule_live_transcription(state, call)
            return 200, "application/xml", str(transcript._live_twiml(state, call))
        return 200, "application/xml", twilio.waiting_twiml()
    if action == "voicemail-drop":
        settings = state.read_settings()
        text = (
            call.get("voicemail_drop_text")
            or str(settings.get("AI_VOICEMAIL_MESSAGE") or "").strip()
            or "Hi. We tried to reach you. Please call back when you can."
        )
        return 200, "application/xml", (
            f"<Response><Say>{escape_xml(text)}</Say><Hangup/></Response>"
        )
    if action == "machine":
        return pickup._machine_result(state, call, params)
    if action == "transcript":
        return transcript._transcription_event(state, call, params)
    if action == "hangup":
        ended._call_ended(state, call, params)
        return 200, "text/plain", "OK"
    if action == "agent-ended" and call["kind"] == "agent":
        ended._agent_call_ended(state)
        return 200, "application/xml", "<Response/>"
    return 404, "text/plain", "Unknown callback"

def handle_client_voice(state, params):
    if not voice_session.uses_browser_agent_leg(state):
        return 200, "application/xml", "<Response><Hangup/></Response>"
    token = params.get("DeskToken") or params.get("CallToken") or ""
    with state.lock:
        call = state.calls.get(token)
        if not call or call["kind"] != "agent" or call["cancelled"] or not state.running:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        call_uuid = params.get("CallSid", "")
        if call_uuid:
            call["call_uuid"] = call_uuid
            state.agent_call_uuid = call_uuid
        state.agent_ready = True
        state.last_event = "Computer audio connected"
    state.record_activity("Browser audio joined the conference", "call")
    threading.Thread(target=slots.fill_slots, args=(state,), daemon=True).start()
    xml = (
        f'<Response><Dial action="{escape_xml(twilio._url(state, call, "agent-ended"))}" method="POST">'
        '<Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="false">'
        f'{escape_xml(state.conference)}</Conference></Dial></Response>'
    )
    return 200, "application/xml", xml

def hangup_active(state):
    with state.lock:
        call = state.active or next(
            (
                item for item in state.in_flight.values()
                if item["kind"] == "prospect" and item["state"] in ("ringing", "creating")
            ),
            None,
        )
        call_uuid = call.get("call_uuid") if call else None
        if call and state.running:
            ai_mode = getattr(state, "ai_agent_mode", False)
            if call is state.active or call.get("picked_up"):
                call["wrapping"] = True
                if not ai_mode:
                    state.pending_outcome = call["lead_id"]
                state.last_event = "Call ended; choose a disposition" if not ai_mode else "Call ended"
            else:
                call["handled"] = True
                call["cancelled"] = True
                call["state"] = "ended"
                state.in_flight.pop(call["token"], None)
                if not ai_mode:
                    state.pending_outcome = call["lead_id"]
                state.last_event = "Call ended; choose a disposition" if not ai_mode else "Call ended"
    if call_uuid:
        threading.Thread(target=twilio._hangup_call, args=(state, call_uuid), daemon=True).start()
    return projection.public_state(state)

def skip_active(state):
    with state.lock:
        call = state.active or next(
            (item for item in state.in_flight.values() if item["kind"] == "prospect"),
            None,
        )
        if not call:
            raise ValueError("There is no prospect call to skip.")
        lead_id = call.get("lead_id")
        picked_up = bool(call.get("picked_up")) or state.active is call
    if not picked_up and lead_id:
        return queue.pass_next(state, lead_id)
    with state.lock:
        call_uuid = call.get("call_uuid")
        call["wrapping"] = True
        call["handled"] = True
        if not getattr(state, "ai_agent_mode", False):
            state.pending_outcome = lead_id if state.running else None
        state.last_event = "Prospect skipped; choose a disposition" if state.running else "Prospect skipped"
    if not state.running and lead_id:
        queue.schedule_callback(state, lead_id)
        rules._bump(state, OUTCOME_METRIC["dialed"])
        rules._flush_metrics(state)
    ai_mode = getattr(state, "ai_agent_mode", False)
    state.record_activity(
        "Prospect skipped" if ai_mode else "Prospect skipped; choose a disposition",
        "call",
    )
    if call_uuid:
        threading.Thread(target=twilio._hangup_call, args=(state, call_uuid), daemon=True).start()
    return projection.public_state(state)
