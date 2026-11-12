"""Single write path for live conversation text (Twilio today, Cartesia bridge later)."""

from datetime import datetime, timezone

from shared.vocabulary import TRANSCRIPT_SOURCE_TWILIO


def append_partial(state, storage_call, *, speaker, text, timestamp=None, track="", source=TRANSCRIPT_SOURCE_TWILIO):
    if not storage_call or not text:
        return
    text = str(text).strip()
    if not text:
        return
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    partial = {
        "timestamp": timestamp,
        "speaker": speaker,
        "text": text,
        "final": False,
        "source": source,
    }
    with state.lock:
        storage_call.setdefault("transcript_partials", {})[track or speaker] = partial
        storage_call["transcript_source"] = source


def append_final(
    state,
    storage_call,
    *,
    speaker,
    text,
    timestamp=None,
    segment_id=None,
    track="",
    source=TRANSCRIPT_SOURCE_TWILIO,
    persist_crm=True,
):
    if not storage_call or not text:
        return False
    text = str(text).strip()
    if not text:
        return False
    timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    leg_id = storage_call.get("call_uuid") or storage_call["token"]
    segment_id = segment_id or f"{leg_id}:{source}:{track or speaker}:{timestamp}"
    lead_id = storage_call.get("lead_id")
    if persist_crm and lead_id:
        try:
            state.crm.append_transcript(lead_id, {
                "id": segment_id,
                "timestamp": timestamp,
                "speaker": speaker,
                "text": text,
            })
        except (KeyError, ValueError, OSError) as exc:
            state.record_activity(f"Could not save transcript segment: {exc}", "error")
            return False
    line = {
        "id": segment_id,
        "timestamp": timestamp,
        "speaker": speaker,
        "text": text,
        "final": True,
        "source": source,
    }
    with state.lock:
        storage_call.setdefault("transcript_partials", {}).pop(track or speaker, None)
        lines = storage_call.setdefault("transcript_lines", [])
        if any(item.get("id") == segment_id for item in lines):
            return True
        lines.append(line)
        storage_call["transcript_source"] = source
    return True


def commit_partials(state, storage_call, *, allowed_speakers=("Agent", "Prospect"), source=TRANSCRIPT_SOURCE_TWILIO):
    """Promote in-progress partial lines when a transcript session closes."""
    if not storage_call:
        return
    with state.lock:
        partials = list(storage_call.get("transcript_partials", {}).items())
        storage_call["transcript_partials"].clear()
        leg_id = storage_call.get("call_uuid") or storage_call["token"]
    for track, partial in partials:
        text = str((partial or {}).get("text") or "").strip()
        speaker = (partial or {}).get("speaker") or ""
        if not text or speaker not in allowed_speakers:
            continue
        timestamp = (partial or {}).get("timestamp") or datetime.now(timezone.utc).isoformat()
        segment_id = f"{leg_id}:{track or speaker}:partial:{timestamp}"
        append_final(
            state,
            storage_call,
            speaker=speaker,
            text=text,
            timestamp=timestamp,
            segment_id=segment_id,
            track=track,
            source=(partial or {}).get("source") or source,
        )
