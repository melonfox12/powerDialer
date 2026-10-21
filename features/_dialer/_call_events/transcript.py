"""Live conference TwiML and transcription callbacks."""

import json
import time
from datetime import datetime, timezone

from twilio.twiml.voice_response import VoiceResponse

from features._dialer import twilio

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
        status_callback_url=twilio._url(state, call, "transcript"),
        status_callback_method="POST",
        name=f"crm-{call['token']}",
        track="both_tracks",
        inbound_track_label="prospect",
        outbound_track_label="agent",
        partial_results=True,
        language_code="en-US",
        speech_model="telephony",
        enable_automatic_punctuation=True,
    )

def _speaker_for(track):
    value = str(track or "").lower()
    if "inbound" in value:
        return "Prospect"
    if "outbound" in value:
        return "Agent"
    return ""

def _call_still_connected(state, call):
    with state.lock:
        return bool(
            state.running
            and state.active is call
            and not call.get("end_processed")
            and not call.get("cancelled")
        )

def _remember_line(state, call, segment_id, timestamp, speaker, text, track):
    try:
        state.crm.append_transcript(call["lead_id"], {
            "id": segment_id,
            "timestamp": timestamp,
            "speaker": speaker,
            "text": text,
        })
    except (KeyError, ValueError, OSError) as exc:
        state.record_activity(f"Could not save transcript segment: {exc}", "error")
        return False
    line = {"id": segment_id, "timestamp": timestamp, "speaker": speaker, "text": text, "final": True}
    with state.lock:
        call["transcript_partials"].pop(track or speaker, None)
        lines = call.setdefault("transcript_lines", [])
        if any(item.get("id") == segment_id for item in lines):
            return True
        lines.append(line)
    return True

def _commit_partials(state, call):
    """Keep the in-progress sentence when Twilio closes the transcript session."""
    with state.lock:
        partials = list(call.get("transcript_partials", {}).items())
        call["transcript_partials"].clear()
    for track, partial in partials:
        text = str((partial or {}).get("text") or "").strip()
        speaker = (partial or {}).get("speaker") or _speaker_for(track)
        if not text or speaker not in ("Agent", "Prospect"):
            continue
        timestamp = (partial or {}).get("timestamp") or datetime.now(timezone.utc).isoformat()
        segment_id = f"{call.get('call_uuid') or call['token']}:{track}:partial:{timestamp}"
        _remember_line(state, call, segment_id, timestamp, speaker, text, track)

def _resume_transcription(state, call):
    """Twilio ends a transcript session on its own. Open another while the call is up."""
    with state.lock:
        if not _call_still_connected(state, call):
            return
        now = time.monotonic()
        if now - float(call.get("transcription_restart_at") or 0) < 2:
            return
        call["transcription_restart_at"] = now
        count = int(call.get("transcription_restarts") or 0) + 1
        call["transcription_restarts"] = count
        call_uuid = call.get("call_uuid")
    try:
        twilio._start_live_transcription(
            state, call_uuid, twilio._url(state, call, "transcript"), f"crm-{call['token']}-{count}",
        )
    except (twilio.TwilioError, KeyError) as exc:
        with state.lock:
            call["transcription_restart_at"] = 0
        state.record_activity(f"Could not resume the live transcript: {exc}", "error")
        return
    state.record_activity("Live transcript resumed", "transcription")

def _transcription_event(state, call, params):
    event = params.get("TranscriptionEvent", "")
    if event == "transcription-started":
        with state.lock:
            call["transcribing"] = True
        state.record_activity("Live transcript connected", "transcription")
        return 200, "text/plain", "OK"
    if event == "transcription-stopped":
        _commit_partials(state, call)
        with state.lock:
            call["transcribing"] = False
            still_connected = _call_still_connected(state, call)
        if still_connected:
            _resume_transcription(state, call)
        else:
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
    speaker = _speaker_for(track)
    if not speaker:
        return 200, "text/plain", "OK"
    timestamp = params.get("Timestamp") or datetime.now(timezone.utc).isoformat()
    final = str(params.get("Final", "false")).lower() == "true"
    partial = {"timestamp": timestamp, "speaker": speaker, "text": text, "final": final}
    if not final:
        with state.lock:
            call["transcript_partials"][track or speaker] = partial
        return 200, "text/plain", "OK"

    segment_id = f"{call.get('call_uuid') or call['token']}:{track}:{params.get('SequenceId', timestamp)}"
    if _remember_line(state, call, segment_id, timestamp, speaker, text, track):
        state.record_activity(f"Transcript updated · {speaker}", "transcription")
    return 200, "text/plain", "OK"
