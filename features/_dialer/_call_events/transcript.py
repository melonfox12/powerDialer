"""Live conference TwiML and transcription callbacks."""

import json
from datetime import datetime, timezone

from twilio.twiml.voice_response import VoiceResponse

from features._dialer import twilio_api

def _live_twiml(state, call):
    response = VoiceResponse()
    with state.lock:
        start_transcription = not call.get("transcription_started")
        call["transcription_started"] = True
    if start_transcription:
            _start_transcription(state, response, call)
    response.dial().conference(
        state.conference,
        beep="false",
        start_conference_on_enter="true",
        end_conference_on_exit="false",
    )
    return response

def _start_transcription(state, response, call):
    response.start().transcription(
            status_callback_url=twilio_api._url(state, call, "transcript"),
        name=f"crm-{call['token']}",
        track="both_tracks",
        inbound_track_label="prospect",
        outbound_track_label="agent",
        partial_results=True,
        language_code="en-US",
        speech_model="telephony",
        enable_automatic_punctuation=True,
    )

def _transcription_event(state, call, params):
    event = params.get("TranscriptionEvent", "")
    if event == "transcription-started":
        with state.lock:
            call["transcribing"] = True
        state.record_activity("Live transcript connected", "transcription")
        return 200, "text/plain", "OK"
    if event == "transcription-stopped":
        with state.lock:
            call["transcribing"] = False
            call["transcript_partials"].clear()
        state.record_activity("Live transcript ended", "transcription")
        return 200, "text/plain", "OK"
    if event == "transcription-error":
        error = params.get("TranscriptionError", "Transcription unavailable")
        state.record_activity(f"Live transcription error: {error}", "error")
        return 200, "text/plain", "OK"
    if event != "transcription-content":
        return 200, "text/plain", "OK"
    try:
        data = json.loads(params.get("TranscriptionData", "{}"))
    except (TypeError, ValueError):
        data = {}
    text = str(data.get("transcript", "")).strip()
    if not text:
        return 200, "text/plain", "OK"
    track = params.get("Track", "")
    speaker = "Prospect" if track == "inbound_track" else "Agent" if track == "outbound_track" else "Unknown"
    timestamp = params.get("Timestamp") or datetime.now(timezone.utc).isoformat()
    final = str(params.get("Final", "false")).lower() == "true"
    partial = {"timestamp": timestamp, "speaker": speaker, "text": text, "final": final}
    if not final:
        with state.lock:
            call["transcript_partials"][track or speaker] = partial
        return 200, "text/plain", "OK"

    segment_id = f"{call.get('call_uuid') or call['token']}:{track}:{params.get('SequenceId', timestamp)}"
    try:
        state.crm.append_transcript(call["lead_id"], {
            "id": segment_id,
            "timestamp": timestamp,
            "speaker": speaker,
            "text": text,
        })
    except (KeyError, ValueError, OSError) as exc:
        state.record_activity(f"Could not save transcript segment: {exc}", "error")
        return 200, "text/plain", "OK"
    line = {"id": segment_id, "timestamp": timestamp, "speaker": speaker, "text": text, "final": True}
    with state.lock:
        call["transcript_partials"].pop(track or speaker, None)
        lines = call.setdefault("transcript_lines", [])
        lines.append(line)
        del lines[:-80]
    state.record_activity(f"Transcript updated · {speaker}", "transcription")
    return 200, "text/plain", "OK"
