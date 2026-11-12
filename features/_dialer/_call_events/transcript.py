"""Live conference TwiML and transcription callbacks."""

import json
import threading
import time
from datetime import datetime, timezone

from features import ai_voice_runtime
from features._dialer import live_transcript, twilio, voice_session
from shared.vocabulary import TRANSCRIPT_SOURCE_TWILIO

def _live_twiml(state, call):
    """Bridge the prospect into the agent conference. Transcription starts after media is up."""
    conf = twilio.escape_xml(state.conference)
    return (
        "<Response><Dial>"
        f'<Conference beep="false" startConferenceOnEnter="true" endConferenceOnExit="false">{conf}</Conference>'
        "</Dial></Response>"
    )


def _agent_call(state):
    with state.lock:
        token = state.agent_call_token
        return state.calls.get(token) if token else None


def _storage_call(state, call):
    """Prospect row that receives transcript lines (agent leg events attach to the live prospect)."""
    with state.lock:
        if call.get("kind") == "agent":
            pinned = call.get("transcription_prospect_token")
            if pinned and pinned in state.calls:
                return state.calls[pinned]
        if call.get("lead_id"):
            return call
    return None


def _speaker_for(track, call_kind, track_label=""):
    value = str(track or "").lower()
    inbound = "inbound" in value
    outbound = "outbound" in value
    if call_kind == "agent":
        if inbound:
            return "Agent"
        if outbound:
            return "Prospect"
    elif inbound:
        return "Prospect"
    elif outbound:
        return "Agent"
    label = str(track_label or track or "").lower()
    if label in ("agent", "outbound_track_label"):
        return "Agent" if call_kind == "agent" else "Prospect"
    if label in ("prospect", "customer", "inbound_track_label"):
        return "Prospect" if call_kind == "agent" else "Agent"
    if "agent" in label and "prospect" not in label:
        return "Agent" if call_kind == "agent" else "Prospect"
    if "prospect" in label or "customer" in label:
        return "Prospect" if call_kind == "agent" else "Agent"
    return ""


def schedule_live_transcription(state, prospect_call):
    """Start live transcription on the agent browser leg once the prospect is in the conference.

    The PSTN leg's outbound mix often misses agent speech; the browser leg hears the full conference.
    """
    with state.lock:
        agent = _agent_call(state)
        agent_uuid = (state.agent_call_uuid or (agent or {}).get("call_uuid")) if agent else None
        if agent and agent_uuid:
            agent["transcription_prospect_token"] = prospect_call["token"]
            if agent.get("transcribing"):
                return
            media_call = agent
            call_uuid = agent_uuid
            callback_call = agent
            name = f"crm-{prospect_call['token']}"
            agent["transcription_started"] = True
        elif not prospect_call.get("transcription_started") and prospect_call.get("call_uuid"):
            prospect_call["transcription_started"] = True
            media_call = prospect_call
            call_uuid = prospect_call.get("call_uuid")
            callback_call = prospect_call
            name = f"crm-{prospect_call['token']}"
        else:
            return
        callback_url = twilio._url(state, callback_call, "transcript")

    def _start():
        time.sleep(0.4)
        try:
            twilio._start_live_transcription(state, call_uuid, callback_url, name)
        except (twilio.TwilioError, KeyError) as exc:
            with state.lock:
                media_call["transcription_started"] = False
                if media_call.get("kind") == "agent":
                    media_call.pop("transcription_prospect_token", None)
            state.record_activity(f"Could not start live transcript: {exc}", "error")

    threading.Thread(target=_start, daemon=True).start()


def _live_prospect(state, media_call):
    with state.lock:
        if media_call.get("kind") == "agent":
            token = media_call.get("transcription_prospect_token")
            prospect = state.calls.get(token) if token else None
        else:
            prospect = media_call
        if not prospect or prospect.get("kind") == "agent":
            return None
        return prospect


def _call_still_connected(state, media_call):
    with state.lock:
        prospect = _live_prospect(state, media_call)
        if prospect is None:
            prospect = media_call if media_call.get("lead_id") else None
        if prospect is None:
            return False
        return bool(
            state.running
            and state.active is prospect
            and not prospect.get("end_processed")
            and not prospect.get("cancelled")
        )


def _resume_transcription(state, media_call, name_prefix):
    """Twilio ends a transcript session on its own. Open another while the call is up."""
    with state.lock:
        if not _call_still_connected(state, media_call):
            return
        now = time.monotonic()
        if now - float(media_call.get("transcription_restart_at") or 0) < 2:
            return
        media_call["transcription_restart_at"] = now
        count = int(media_call.get("transcription_restarts") or 0) + 1
        media_call["transcription_restarts"] = count
        call_uuid = media_call.get("call_uuid")
    try:
        twilio._start_live_transcription(
            state,
            call_uuid,
            twilio._url(state, media_call, "transcript"),
            f"{name_prefix}-{count}",
        )
    except (twilio.TwilioError, KeyError) as exc:
        with state.lock:
            media_call["transcription_restart_at"] = 0
        state.record_activity(f"Could not resume the live transcript: {exc}", "error")
        return
    state.record_activity("Live transcript resumed", "transcription")


def _transcription_event(state, call, params):
    storage = _storage_call(state, call)
    call_kind = call.get("kind") or "prospect"
    event = params.get("TranscriptionEvent", "")
    if event == "transcription-started":
        with state.lock:
            call["transcribing"] = True
            if storage:
                storage["transcribing"] = True
        state.record_activity("Live transcript connected", "transcription")
        return 200, "text/plain", "OK"
    if event == "transcription-stopped":
        if storage:
            live_transcript.commit_partials(state, storage, source=TRANSCRIPT_SOURCE_TWILIO)
        with state.lock:
            call["transcribing"] = False
            if storage:
                storage["transcribing"] = False
        still_connected = _call_still_connected(state, call)
        if still_connected:
            prefix = f"crm-{storage['token']}" if storage else f"crm-{call['token']}"
            _resume_transcription(state, call, prefix)
        else:
            state.record_activity("Live transcript ended", "transcription")
        return 200, "text/plain", "OK"
    if event == "transcription-error":
        error = params.get("TranscriptionError", "Transcription unavailable")
        state.record_activity(f"Live transcription error: {error}", "error")
        if _call_still_connected(state, call):
            prefix = f"crm-{storage['token']}" if storage else f"crm-{call['token']}"
            _resume_transcription(state, call, prefix)
        return 200, "text/plain", "OK"
    if event != "transcription-content":
        return 200, "text/plain", "OK"
    if not storage:
        return 200, "text/plain", "OK"
    try:
        data = json.loads(params.get("TranscriptionData", "{}"))
    except (TypeError, ValueError):
        data = {}
    text = str(data.get("transcript", "")).strip()
    if not text:
        return 200, "text/plain", "OK"
    track = params.get("Track", "")
    track_label = params.get("TrackLabel") or params.get("InboundTrackLabel") or params.get("OutboundTrackLabel") or ""
    speaker = _speaker_for(track, call_kind, track_label)
    if not speaker:
        return 200, "text/plain", "OK"
    timestamp = params.get("Timestamp") or datetime.now(timezone.utc).isoformat()
    final = str(params.get("Final", "false")).lower() == "true"
    if not final:
        live_transcript.append_partial(
            state,
            storage,
            speaker=speaker,
            text=text,
            timestamp=timestamp,
            track=track,
            source=TRANSCRIPT_SOURCE_TWILIO,
        )
        return 200, "text/plain", "OK"

    session_id = params.get("TranscriptionSid", "")
    leg_id = call.get("call_uuid") or call["token"]
    segment_id = f"{leg_id}:{session_id}:{track}:{params.get('SequenceId', timestamp)}"
    if live_transcript.append_final(
        state,
        storage,
        speaker=speaker,
        text=text,
        timestamp=timestamp,
        segment_id=segment_id,
        track=track,
        source=TRANSCRIPT_SOURCE_TWILIO,
    ):
        if speaker == "Prospect" and voice_session.is_ai_voice(state):
            session = ai_voice_runtime.get_session(state, storage.get("bridge_session_id") or "")
            if not (session and session.get("stream_active")):
                ai_voice_runtime.on_prospect_text(state, storage, text, source="twilio")
        state.record_activity(f"Transcript updated · {speaker}", "transcription")
    return 200, "text/plain", "OK"
