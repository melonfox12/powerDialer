"""Dial and CRM queue policy: who may be dialed, caps, repair, pool order, and live contact.

Constants live in shared.vocabulary; this module is the only place for rules that combine them.
"""

from datetime import datetime, timedelta, timezone

from shared.infra import utc_now
from shared.vocabulary import (
    CALLBACK_TIMER_MIGRATION_FIELD,
    CALLBACK_TIMER_MIGRATION_SHIFT_HOURS,
    DEFAULT_BUSINESS_TYPE,
    DEFAULT_DIAL_POOL_STATUS,
    DIAL_POOL_STATUSES,
    LEGACY_CONNECTED_ANSWERS,
    MANUAL_CALLBACK_HOURS,
    MAX_DIAL_ATTEMPTS_BEFORE_DISQUALIFY,
    NEVER_DIAL_STATUSES,
    NO_PICKUP_CALLBACK_HOURS,
    NOT_CONNECTED_CALL_ANSWERS,
    canonical_status,
)

CALLBACK_TIMER_MIGRATION_SHIFT = timedelta(hours=CALLBACK_TIMER_MIGRATION_SHIFT_HOURS)

RECENT_DIAL_WINDOW = timedelta(hours=12)
RACE_LOST = "race_lost"
CANCELLED = "cancelled"
DEAD_LINE = "dead_line"
NO_PICKUP_CALLBACK = timedelta(hours=NO_PICKUP_CALLBACK_HOURS)
RETRY_AFTER = {
    "no_answer": NO_PICKUP_CALLBACK,
    "voicemail": NO_PICKUP_CALLBACK,
    RACE_LOST: NO_PICKUP_CALLBACK,
    CANCELLED: NO_PICKUP_CALLBACK,
    DEAD_LINE: NO_PICKUP_CALLBACK,
}
MANUAL_CALLBACK = timedelta(hours=MANUAL_CALLBACK_HOURS)
CALLBACK_HOLD = max(MANUAL_CALLBACK, NO_PICKUP_CALLBACK) + timedelta(seconds=2)


def normalize_phone(raw):
    text = str(raw or "").strip()
    digits = "".join(char for char in text if char.isdigit())
    if text.startswith("+") and 8 <= len(digits) <= 15:
        return "+" + digits
    if len(digits) == 10:
        return "+1" + digits
    if len(digits) == 11 and digits.startswith("1"):
        return "+" + digits
    return None


def location_text(lead, key):
    direct = str((lead or {}).get(key) or "").strip()
    if direct:
        return direct
    for name, value in ((lead or {}).get("fields") or {}).items():
        if str(name).strip().lower() == key:
            return str(value or "").strip()
    return ""


def _folded(value):
    return " ".join(str(value or "").split()).casefold()


def is_connected_call_log_entry(entry):
    """True when the agent was bridged to the prospect on this dial (picked up)."""
    connected = entry.get("connected")
    if isinstance(connected, bool):
        return connected
    answered = str(entry.get("answered_by") or "")
    if answered in NOT_CONNECTED_CALL_ANSWERS:
        return False
    return answered in LEGACY_CONNECTED_ANSWERS


def lead_has_live_contact(lead):
    """Transcript text or any connected call_log row counts as live contact."""
    for segment in lead.get("transcript") or []:
        if str(segment.get("text") or "").strip():
            return True
    for entry in lead.get("call_log") or []:
        if is_connected_call_log_entry(entry):
            return True
    return False


def total_dial_count(lead):
    """Rows on Total dials: one per call_log entry."""
    return len(lead.get("call_log") or [])


def dial_cap_reached(lead):
    return total_dial_count(lead) >= MAX_DIAL_ATTEMPTS_BEFORE_DISQUALIFY


def apply_dial_cap_to_lead(lead):
    """Mark no_answer_disqualified after enough dials with no live contact. Returns True when changed."""
    if not dial_cap_reached(lead):
        return False
    if lead_has_live_contact(lead):
        return False
    if canonical_status(lead.get("status")) in NEVER_DIAL_STATUSES:
        return False
    lead["status"] = "no_answer_disqualified"
    lead["scheduled_until"] = None
    return True


def repair_dial_status_for_lead(lead):
    """Fix auto-disqualified statuses mistaken for sales DQ. Returns next status or None."""
    status = canonical_status(lead.get("status"))
    has_live = lead_has_live_contact(lead)
    at_cap = dial_cap_reached(lead)
    if status == "disqualified":
        if has_live:
            return None
        return "no_answer_disqualified" if at_cap else "new"
    if status == "no_answer_disqualified":
        if has_live:
            return "disqualified"
        if not at_cap:
            return "new"
    return None


def is_never_dial_status(status):
    return canonical_status(status) in NEVER_DIAL_STATUSES


def resolve_pool_status(value):
    status = canonical_status(value or DEFAULT_DIAL_POOL_STATUS)
    return status if status in DIAL_POOL_STATUSES else DEFAULT_DIAL_POOL_STATUS


def unique_business_types(leads):
    """Distinct non-empty industry / business_type values from CRM rows, sorted for UI."""
    seen = {}
    for lead in leads or []:
        text = str((lead or {}).get("business_type") or "").strip()
        if not text:
            continue
        folded = text.casefold()
        if folded not in seen:
            seen[folded] = text
    return sorted(seen.values(), key=lambda value: value.casefold())


def lead_matches_dial_business_type(lead, selected):
    """True when the prospect's industry matches the dialer filter (case-insensitive)."""
    if not selected:
        return True
    text = str((lead or {}).get("business_type") or DEFAULT_BUSINESS_TYPE).strip().casefold()
    target = str(selected).strip().casefold()
    return bool(target) and text == target


def dial_times(lead):
    log = lead.get("call_log") or []
    if log:
        return [item.get("started_at") or item.get("ended_at") or "" for item in log]
    return [line.get("timestamp") or "" for line in (lead.get("transcript") or [])]


def contact_keys(lead):
    """Phone and person keys used to dedupe the auto-dial pool."""
    keys = set()
    phone = normalize_phone(lead.get("phone"))
    if phone:
        keys.add(("phone", phone))
    name = _folded(lead.get("name"))
    business = _folded(lead.get("business"))
    city = _folded(location_text(lead, "city"))
    state_name = _folded(location_text(lead, "state"))
    if name and (business or city or state_name):
        keys.add(("person", name, business, city, state_name))
    return keys


def identity_key(lead):
    """Name plus location for callback sync between duplicate imports."""
    name = _folded(lead.get("name"))
    if not name:
        return None
    city = _folded(location_text(lead, "city"))
    state_name = _folded(location_text(lead, "state"))
    if city or state_name:
        place = (city, state_name)
    else:
        place = ("", _folded(lead.get("timezone")))
    return (name, place)


def callback_due(lead):
    try:
        moment = datetime.fromisoformat(str(lead.get("scheduled_until") or ""))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment


def apply_callback_timer_migration_to_lead(lead, now):
    """One-time per lead: shift open callbacks forward after the 48h → 2h policy change."""
    if lead.get("status") != "call" or not lead.get("scheduled_until"):
        return False
    fields = lead.setdefault("fields", {})
    if fields.get(CALLBACK_TIMER_MIGRATION_FIELD):
        return False
    due = callback_due(lead)
    fields[CALLBACK_TIMER_MIGRATION_FIELD] = True
    if due is None:
        return False
    new_due = due - CALLBACK_TIMER_MIGRATION_SHIFT
    if new_due <= now:
        lead["status"] = "new"
        lead["scheduled_until"] = None
    else:
        lead["scheduled_until"] = new_due.isoformat()
    return True


def retry_wait_for_log_entry(entry):
    """How long before this dial-log row allows the same prospect back in the auto pool."""
    answered = str((entry or {}).get("answered_by") or "")
    if answered:
        return RETRY_AFTER.get(answered, RECENT_DIAL_WINDOW)
    return NO_PICKUP_CALLBACK


def open_dial_lead_ids(leads):
    """Prospects with a call_log row still in progress (dialed but not finished)."""
    ids = set()
    for lead in leads or []:
        lead_id = lead.get("id")
        if not lead_id:
            continue
        for entry in lead.get("call_log") or []:
            started = str(entry.get("started_at") or "").strip()
            ended = str(entry.get("ended_at") or "").strip()
            answered = str(entry.get("answered_by") or "").strip()
            if started and not ended and not answered:
                ids.add(lead_id)
                break
    return ids


def dial_windows(lead):
    log = lead.get("call_log") or []
    if log:
        return [
            (item.get("started_at") or item.get("ended_at") or "", retry_wait_for_log_entry(item))
            for item in log
        ]
    return [(raw, RECENT_DIAL_WINDOW) for raw in dial_times(lead)]


def dialed_recently(lead, now=None):
    moment_now = now or utc_now()
    for raw, wait in dial_windows(lead):
        try:
            moment = datetime.fromisoformat(str(raw))
        except (TypeError, ValueError):
            continue
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        if moment > moment_now - wait:
            return True
    return False


def off_limits_contact_keys(leads, busy_ids, now, pool_status):
    """Contact keys for people who must not be auto-dialed right now."""
    keys = set()
    for lead in leads:
        if (
            canonical_status(lead.get("status")) != pool_status
            or lead["id"] in busy_ids
            or dialed_recently(lead, now)
        ):
            keys |= contact_keys(lead)
    return keys


def pool_leads(
    leads,
    *,
    pool_status,
    busy_ids,
    now=None,
    selected_timezone=None,
    selected_business_type=None,
    anchor_id=None,
):
    """Ordered, deduped prospects eligible for auto-dial in the active pool mode."""
    moment = now or utc_now()
    pool_status = resolve_pool_status(pool_status)
    off_limits = off_limits_contact_keys(leads, busy_ids, moment, pool_status)
    indexed = [
        (index, lead) for index, lead in enumerate(leads)
        if canonical_status(lead.get("status")) == pool_status and lead["id"] not in busy_ids
        and not dialed_recently(lead, moment) and not (contact_keys(lead) & off_limits)
        and lead_matches_dial_business_type(lead, selected_business_type)
    ]
    if selected_timezone:
        zone = selected_timezone
        indexed = [
            (index, lead) for index, lead in indexed
            if lead["id"] == anchor_id or (lead.get("timezone") or "Unknown") == zone
        ]
    indexed.sort(key=lambda item: (bool(item[1].get("passed_at")), item[1].get("passed_at") or "", item[0]))
    ordered = [lead for _index, lead in indexed]
    if anchor_id:
        held = [lead for lead in ordered if lead["id"] == anchor_id]
        rest = [lead for lead in ordered if lead["id"] != anchor_id]
        ordered = held + rest
    taken = set()
    people = []
    for lead in ordered:
        keys = contact_keys(lead)
        if keys & taken:
            continue
        taken |= keys
        people.append(lead)
    return people


def leads_for_timezone_counts(leads, pool_status, now=None, selected_business_type=None):
    """Prospects that count toward timezone menu buckets for the active pool."""
    moment = now or utc_now()
    pool_status = resolve_pool_status(pool_status)
    return [
        lead for lead in leads
        if canonical_status(lead.get("status")) == pool_status and not dialed_recently(lead, moment)
        and lead_matches_dial_business_type(lead, selected_business_type)
    ]


def callback_sync_plan(leads, now):
    """New prospects that should inherit an open callback from a matching Total dials row."""
    sources = {}
    for lead in leads or []:
        if lead.get("status") != "call" or not dial_times(lead):
            continue
        due = callback_due(lead)
        if due is None:
            continue
        remaining = due - now
        if remaining <= timedelta(0) or remaining > CALLBACK_HOLD:
            continue
        key = identity_key(lead)
        if key is None:
            continue
        current = sources.get(key)
        if current is None or due > current[0]:
            sources[key] = (due, due.isoformat(), lead.get("id"))
    copies = []
    for lead in leads or []:
        if lead.get("status") != "new":
            continue
        key = identity_key(lead)
        source = sources.get(key)
        if source is None or lead.get("id") == source[2]:
            continue
        copies.append({"id": lead["id"], "scheduled_until": source[1]})
    return copies


def manual_lead_blocked(lead, leads, active_lead_ids):
    """Whether a pinned manual dial target cannot be claimed."""
    if (
        not lead
        or not lead.get("phone")
        or is_never_dial_status(lead.get("status"))
        or lead["id"] in active_lead_ids
    ):
        return True
    keys = contact_keys(lead)
    return any(
        keys & contact_keys(other) for other in leads
        if other["id"] != lead["id"]
        and (other["id"] in active_lead_ids or is_never_dial_status(other.get("status")))
    )
