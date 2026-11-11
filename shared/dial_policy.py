"""Dial and CRM queue policy: who may be dialed, caps, repair, pool order, and live contact.

Constants live in shared.vocabulary; this module is the only place for rules that combine them.
"""

from datetime import datetime, timedelta, timezone

from shared.infra import utc_now
from shared.vocabulary import (
    AGENT_POOL_SIZE,
    AGENT_RESERVED_ID_FIELD,
    AGENT_RESERVED_NAME_FIELD,
    AGENT_USE_STATUS,
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
# Explicit CRM statuses that stay as-is when a Total dials row is written.
TOTAL_DIALS_PRESERVED_STATUSES = frozenset({
    "contact_engaged",
    "qualified",
    "booked",
    "proposal_sent",
    "closed",
})


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


DIAL_LOG_LOCAL_TIMEZONE = "America/New_York"


def dial_entry_calendar_date(entry):
    item = entry or {}
    for key in ("started_at", "ended_at"):
        text = str(item.get(key) or "")
        if len(text) >= 10:
            return text[:10]
    return ""


def dial_entry_local_calendar_dates(entry, tz_name=DIAL_LOG_LOCAL_TIMEZONE):
    """Local calendar dates for a dial row (matches Total dials “today” for Eastern ops)."""
    from zoneinfo import ZoneInfo

    dates = set()
    zone = ZoneInfo(tz_name)
    item = entry or {}
    for key in ("started_at", "ended_at"):
        text = str(item.get(key) or "").strip()
        if not text:
            continue
        parsed = text.replace("Z", "+00:00")
        try:
            moment = datetime.fromisoformat(parsed)
            if moment.tzinfo is None:
                moment = moment.replace(tzinfo=timezone.utc)
            dates.add(moment.astimezone(zone).date().isoformat())
        except ValueError:
            if len(text) >= 10:
                dates.add(text[:10])
    return dates


def lead_created_on_date(lead, date_prefix):
    return str((lead or {}).get("created_at") or "").startswith(str(date_prefix or ""))


def lead_has_dial_on_date(lead, date_prefix, archived_rows=()):
    prefix = str(date_prefix or "")
    if not prefix:
        return False
    for entry in (lead or {}).get("call_log") or []:
        if prefix in dial_entry_local_calendar_dates(entry) or dial_entry_calendar_date(entry) == prefix:
            return True
    if not (lead or {}).get("call_log") and (lead or {}).get("transcript"):
        stamps = sorted(
            line.get("timestamp") or ""
            for line in (lead or {}).get("transcript") or []
            if line.get("timestamp")
        )
        stub = {"started_at": stamps[0] if stamps else "", "ended_at": stamps[-1] if stamps else ""}
        if prefix in dial_entry_local_calendar_dates(stub):
            return True
    lead_id = (lead or {}).get("id")
    for row in archived_rows or ():
        if lead_id and str(row.get("lead_id") or "") not in ("", lead_id):
            continue
        wrapped = row.get("entry") if isinstance(row, dict) else None
        entry = wrapped or row
        if prefix in dial_entry_local_calendar_dates(entry) or dial_entry_calendar_date(entry) == prefix:
            return True
    return False


def lead_ids_with_dial_on_local_date(leads, archived_rows, date_iso):
    """Prospect ids with any Total dials row on date_iso (live log, archive, transcript stub)."""
    from features._prospects.dial_records import collect_active_dial_records

    target = str(date_iso or "")
    if not target:
        return set()
    ids = set()
    for record in collect_active_dial_records(leads, archived_rows):
        entry = record.get("entry") or {}
        if target not in dial_entry_local_calendar_dates(entry):
            continue
        lead_id = str(record.get("lead_id") or "").strip()
        if lead_id:
            ids.add(lead_id)
    return ids


def apply_static_callback_status(lead, changed_at=None):
    """Callback with no timer — dial pool + pipeline Dialed (ready)."""
    from shared.infra import utc_now

    moment = (changed_at or utc_now()).isoformat()
    previous = canonical_status(lead.get("status"))
    if previous != "dialed" or lead.get("scheduled_until"):
        if previous != "dialed":
            lead.setdefault("status_history", []).append({
                "from_status": previous,
                "to_status": "dialed",
                "changed_at": moment,
            })
        lead["status"] = "dialed"
        lead["scheduled_until"] = None
        return True
    return False


def apply_total_dials_callback_status(lead, entry=None, now=None):
    """After a Total dials row is saved, set Callback (2h) unless the prospect has an explicit disposition."""
    moment = (now or utc_now()).replace(microsecond=0)
    status = canonical_status(lead.get("status"))
    if status in NEVER_DIAL_STATUSES or status in TOTAL_DIALS_PRESERVED_STATUSES:
        return False
    if entry is not None and is_connected_call_log_entry(entry):
        return False
    if status == "dialed":
        due = callback_due(lead)
        if due is not None and due > moment:
            return False
    if status not in ("new", "dialed"):
        return False
    lead["status"] = "dialed"
    lead["scheduled_until"] = (moment + NO_PICKUP_CALLBACK).isoformat()
    return True


def dial_cap_reached(lead):
    return total_dial_count(lead) >= MAX_DIAL_ATTEMPTS_BEFORE_DISQUALIFY


def apply_dial_cap_to_lead(lead):
    """Mark closed after enough dials with no live contact. Returns True when changed."""
    if not dial_cap_reached(lead):
        return False
    if lead_has_live_contact(lead):
        return False
    if canonical_status(lead.get("status")) in NEVER_DIAL_STATUSES:
        return False
    lead["status"] = "closed"
    lead["scheduled_until"] = None
    return True


def repair_dial_status_for_lead(lead):
    """Fix prospects marked closed by the dial cap when the cap no longer applies."""
    status = canonical_status(lead.get("status"))
    has_live = lead_has_live_contact(lead)
    at_cap = dial_cap_reached(lead)
    if status != "closed":
        return None
    if has_live:
        return None
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


def is_dialable_callback(lead, now=None):
    """Callback status with no timer or an elapsed timer — eligible for the New dial pool."""
    if canonical_status(lead.get("status")) != "dialed":
        return False
    moment = now or utc_now()
    due = callback_due(lead)
    if due is None:
        return True
    return due <= moment


def is_agent_reserved(lead):
    return canonical_status((lead or {}).get("status")) == AGENT_USE_STATUS


def agent_reservation_blocks_other_apps(lead, agent_id=None):
    """True when a lead is locked to an AI agent and this caller may not change it."""
    if not is_agent_reserved(lead):
        return False
    if agent_id:
        reserved_id = str((lead or {}).get(AGENT_RESERVED_ID_FIELD) or ((lead or {}).get("fields") or {}).get(AGENT_RESERVED_ID_FIELD) or "").strip()
        return reserved_id != str(agent_id)
    return True


def matches_ai_agent_dial(lead, now=None):
    """AI agents dial only fresh New rows and static Dialed (callback elapsed or no timer)."""
    moment = now or utc_now()
    status = canonical_status(lead.get("status"))
    if status == AGENT_USE_STATUS:
        return True
    if status == "new":
        return True
    if status == "dialed":
        return is_dialable_callback(lead, moment)
    return False


def matches_dial_pool(lead, pool_status, now=None):
    """Whether a prospect belongs in the active dial-pool mode."""
    moment = now or utc_now()
    status = canonical_status(lead.get("status"))
    if status == AGENT_USE_STATUS:
        return False
    pool_status = resolve_pool_status(pool_status)
    if pool_status == "contact_engaged":
        return status == "contact_engaged"
    if pool_status == "new":
        if status == "new":
            return True
        if status == "dialed":
            return is_dialable_callback(lead, moment)
        return False
    return status == pool_status


def apply_callback_timer_migration_to_lead(lead, now):
    """One-time per lead: shift open callbacks forward after the 48h → 2h policy change."""
    if lead.get("status") != "dialed" or not lead.get("scheduled_until"):
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
            not matches_dial_pool(lead, pool_status, now)
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
        if matches_dial_pool(lead, pool_status, moment) and lead["id"] not in busy_ids
        and not dialed_recently(lead, moment) and not (contact_keys(lead) & off_limits)
        and lead_matches_dial_business_type(lead, selected_business_type)
    ]
    if selected_timezone:
        zone = selected_timezone
        indexed = [
            (index, lead) for index, lead in indexed
            if lead["id"] == anchor_id or (lead.get("timezone") or "Unknown") == zone
        ]
    if pool_status == "new":
        indexed.sort(key=lambda item: item[0])
    else:
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
        if matches_dial_pool(lead, pool_status, moment) and not dialed_recently(lead, moment)
        and lead_matches_dial_business_type(lead, selected_business_type)
    ]


def callback_sync_plan(leads, now):
    """New prospects that should inherit an open callback from a matching Total dials row."""
    sources = {}
    for lead in leads or []:
        if lead.get("status") != "dialed" or not dial_times(lead):
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
        or is_agent_reserved(lead)
        or lead["id"] in active_lead_ids
    ):
        return True
    keys = contact_keys(lead)
    return any(
        keys & contact_keys(other) for other in leads
        if other["id"] != lead["id"]
        and (other["id"] in active_lead_ids or is_never_dial_status(other.get("status")) or is_agent_reserved(other))
    )


def global_dialer_pool(
    leads,
    *,
    busy_ids,
    now=None,
    selected_timezone=None,
    selected_business_type=None,
):
    """Every prospect eligible for the manual auto-dial pool app-wide (main caller pool ordering)."""
    return pool_leads(
        leads,
        pool_status=DEFAULT_DIAL_POOL_STATUS,
        busy_ids=busy_ids,
        now=now,
        selected_timezone=selected_timezone,
        selected_business_type=selected_business_type,
    )


def pick_agent_pool_ids(
    leads,
    *,
    busy_ids,
    reserved_ids,
    selected_timezone=None,
    selected_business_type=None,
    limit=AGENT_POOL_SIZE,
):
    """Top N prospects from the global pool that are not already reserved elsewhere."""
    ordered = global_dialer_pool(
        leads,
        busy_ids=busy_ids | set(reserved_ids or ()),
        selected_timezone=selected_timezone,
        selected_business_type=selected_business_type,
    )
    chosen = []
    for lead in ordered:
        if lead["id"] in reserved_ids:
            continue
        if is_agent_reserved(lead):
            continue
        chosen.append(lead["id"])
        if len(chosen) >= limit:
            break
    return chosen


def agent_dial_queue(lead_ids, leads, busy_ids, now=None):
    """Ordered prospects in an agent seat pool that are dialable right now."""
    moment = now or utc_now()
    by_id = {lead["id"]: lead for lead in leads if lead.get("id")}
    queue = []
    for lead_id in lead_ids or []:
        lead = by_id.get(lead_id)
        if not lead or lead_id in busy_ids:
            continue
        if not matches_ai_agent_dial(lead, moment):
            continue
        if dialed_recently(lead, moment):
            continue
        queue.append(lead)
    return queue


def apply_agent_reservation(lead, agent_id, agent_name):
    """Mark a prospect as locked to one AI agent seat."""
    lead[AGENT_RESERVED_NAME_FIELD] = str(agent_name or "").strip()
    lead[AGENT_RESERVED_ID_FIELD] = str(agent_id or "").strip()
    fields = lead.setdefault("fields", {})
    fields[AGENT_RESERVED_NAME_FIELD] = lead[AGENT_RESERVED_NAME_FIELD]
    fields[AGENT_RESERVED_ID_FIELD] = lead[AGENT_RESERVED_ID_FIELD]
    lead["status"] = AGENT_USE_STATUS
    lead["scheduled_until"] = None


def clear_agent_reservation_fields(lead):
    for key in (AGENT_RESERVED_NAME_FIELD, AGENT_RESERVED_ID_FIELD):
        lead.pop(key, None)
        fields = lead.get("fields") or {}
        if key in fields:
            fields.pop(key, None)
            lead["fields"] = fields
