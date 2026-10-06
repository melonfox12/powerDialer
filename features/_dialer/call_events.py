"""Webhook and browser-voice dispatch. Imports pickup, transcript, then ended."""

import threading

from features._dialer._call_events import ended, pickup, transcript
from features._dialer.twilio_api import escape_xml
from shared.vocabulary import OUTCOME_METRIC

def _uuid(params):
    return params.get("CallSid") or params.get("call_uuid") or ""

def handle_webhook(state, token, action, params):
    with state.lock:
        call = state.calls.get(token)
        if not call:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        call_uuid = state._uuid(params)
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
            state._hangup_call(call_uuid)
        return 200, "text/plain", "OK"
    if action == "answer" and call["kind"] == "agent":
        with state.lock:
            state.agent_ready = True
            state.last_event = "Computer audio connected"
        threading.Thread(target=state.fill_slots, daemon=True).start()
        xml = ("<Response><Say>Dialer connected. Stay on the line.</Say><Dial>"
               '<Conference beep="false" startConferenceOnEnter="true" '
               f'endConferenceOnExit="true">{escape_xml(state.conference)}</Conference></Dial></Response>')
        return 200, "application/xml", xml
    if action == "answer":
        if call["kind"] != "prospect" or call["cancelled"] or not state.running:
            return 200, "application/xml", "<Response><Hangup/></Response>"
        state._pickup(call)
        return 200, "application/xml", str(state._live_twiml(call))
    if action == "machine":
        return state._machine_result(call, params)
    if action == "transcript":
        return state._transcription_event(call, params)
    if action == "hangup":
        state._call_ended(call, params)
        return 200, "text/plain", "OK"
    if action == "agent-ended" and call["kind"] == "agent":
        state._agent_call_ended()
        return 200, "application/xml", "<Response/>"
    return 404, "text/plain", "Unknown callback"

def handle_client_voice(state, params):
    token = params.get("CallToken", "")
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
    threading.Thread(target=state.fill_slots, daemon=True).start()
    xml = (
        f'<Response><Dial action="{escape_xml(state._url(call, "agent-ended"))}" method="POST">'
        '<Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="true">'
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
            if call is state.active or call.get("picked_up"):
                call["wrapping"] = True
                state.pending_outcome = call["lead_id"]
                state.last_event = "Call ended; choose a disposition"
            else:
                call["handled"] = True
                call["cancelled"] = True
                call["state"] = "ended"
                state.in_flight.pop(call["token"], None)
                state.pending_outcome = call["lead_id"]
                state.last_event = "Call ended; choose a disposition"
    if call_uuid:
        threading.Thread(target=state._hangup_call, args=(call_uuid,), daemon=True).start()
    return state.public_state()

def skip_active(state):
    with state.lock:
        call = state.active or next(
            (item for item in state.in_flight.values() if item["kind"] == "prospect"),
            None,
        )
        if not call:
            raise ValueError("There is no prospect call to skip.")
        call_uuid = call.get("call_uuid")
        if call.get("picked_up") or state.active is call:
            call["wrapping"] = True
            call["handled"] = True
            state.pending_outcome = call["lead_id"] if state.running else None
            state.last_event = "Prospect skipped; choose a disposition" if state.running else "Prospect skipped"
        else:
            call["handled"] = True
            call["cancelled"] = True
            call["state"] = "skipped"
            state.active = None
            state.in_flight.pop(call["token"], None)
            state.pending_outcome = call["lead_id"] if state.running else None
            state.last_event = "Prospect skipped; choose a disposition" if state.running else "Prospect skipped"
    if not state.running:
        state.crm.set_status(call["lead_id"], "call")
        state._bump(OUTCOME_METRIC["call"])
    state.record_activity("Prospect skipped; choose a disposition", "call")
    if call_uuid:
        threading.Thread(target=state._hangup_call, args=(call_uuid,), daemon=True).start()
    return state.public_state()
