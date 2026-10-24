"""Prospect rules shared by the local and Supabase backends."""

import urllib.parse
from copy import deepcopy
from datetime import datetime, timedelta

from features._prospects.backend_local import LocalBackend
from features._prospects.backend_supabase import SupabaseBackend
from features._prospects.csv_export import csv_bytes_for
from features._prospects.csv_import import parse_csv, update_lead_fields
from shared.infra import utc_now
from shared.vocabulary import (
    CALL_OUTCOME_KEYS,
    MANUAL_CALLBACK_HOURS,
    MAX_DIAL_ATTEMPTS_BEFORE_DISQUALIFY,
    NEVER_DIAL_STATUSES,
    STATUS_KEYS,
    canonical_status,
    lead_has_live_contact,
    parse_prospect_status,
)


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
    """Fix auto-disqualified statuses mistaken for sales DQ. Returns a repair key or None."""
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


class ProspectStore:
    def __init__(self, path=None, *, client=None, user_id=None):
        if client is not None:
            self.backend = SupabaseBackend(client, user_id)
        else:
            self.backend = LocalBackend(path)

    @property
    def lock(self):
        return self.backend.lock

    @property
    def leads(self):
        return self.backend.leads

    @leads.setter
    def leads(self, value):
        self.backend.leads = value

    @property
    def revision(self):
        return self.backend.revision

    def snapshot(self):
        """Every prospect with a current status. Stored records are not rewritten."""
        leads = self.backend.snapshot()
        for lead in leads:
            lead["status"] = canonical_status(lead.get("status"))
        return leads

    def repair_dial_statuses(self):
        """Undo wrongful sales disqualified statuses and align no-answer caps."""
        counts = {"to_new": 0, "to_no_answer_disqualified": 0, "to_disqualified": 0}
        for lead in self.snapshot():
            next_status = repair_dial_status_for_lead(lead)
            if not next_status:
                continue
            self.set_status(lead["id"], next_status, repair=True)
            if next_status == "new":
                counts["to_new"] += 1
            elif next_status == "no_answer_disqualified":
                counts["to_no_answer_disqualified"] += 1
            else:
                counts["to_disqualified"] += 1
        return counts

    def enforce_dial_caps(self, *, repair_misclassified=False):
        """Backfill no_answer_disqualified at the dial cap. Repair runs only when requested (Scan CRM)."""
        repair = self.repair_dial_statuses() if repair_misclassified else {
            "to_new": 0,
            "to_no_answer_disqualified": 0,
            "to_disqualified": 0,
        }
        capped = 0
        for lead in self.snapshot():
            if not dial_cap_reached(lead):
                continue
            if lead_has_live_contact(lead):
                continue
            if canonical_status(lead.get("status")) in NEVER_DIAL_STATUSES:
                continue
            self.set_status(lead["id"], "no_answer_disqualified")
            capped += 1
        return {**repair, "capped": capped}

    def timezone_groups(self, leads=None):
        return self.backend.timezone_groups(leads)

    def csv_bytes(self):
        return self.backend.csv_bytes()

    def add_lead(self, payload):
        return self.backend.add_lead(payload)

    def update_fields(self, lead_id, payload):
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            others = (item.get("phone") for item in leads if item["id"] != lead_id)
            update_lead_fields(lead, payload, others)
            self.backend.save_locked(lead)
            return dict(lead)

    def add_csv(self, data):
        return self.backend.add_csv(data)

    def remove(self, lead_id):
        return self.backend.remove(lead_id)

    def save(self):
        return self.backend.save()

    def defer(self, lead_id):
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            lead["passed_at"] = utc_now().isoformat()
            self.backend.save_locked(lead)
            return dict(lead)

    def set_status(self, lead_id, status, scheduled_until=None, *, repair=False):
        status = parse_prospect_status(status)
        if status not in STATUS_KEYS:
            raise ValueError("Unknown prospect status")
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            if (
                not repair
                and canonical_status(lead.get("status")) in NEVER_DIAL_STATUSES
                and status not in NEVER_DIAL_STATUSES
            ):
                raise ValueError("Booked and disqualified prospects stay out of the queue for good.")
            previous = canonical_status(lead.get("status"))
            changed_at = utc_now().isoformat()
            if previous != status:
                lead.setdefault("status_history", []).append({
                    "from_status": previous,
                    "to_status": status,
                    "changed_at": changed_at,
                })
            lead["status"] = status
            if status == "booked" and not lead.get("booked_at"):
                lead["booked_at"] = changed_at
            if scheduled_until:
                try:
                    due = datetime.fromisoformat(str(scheduled_until))
                except ValueError as exc:
                    raise ValueError("Callback time must be a valid ISO datetime.") from exc
                if due.tzinfo is None:
                    raise ValueError("Callback time must include a timezone.")
                if due <= utc_now():
                    raise ValueError("Callback time must be in the future.")
                lead["scheduled_until"] = due.isoformat()
            else:
                lead["scheduled_until"] = (
                    (utc_now() + timedelta(hours=MANUAL_CALLBACK_HOURS)).isoformat() if status == "call" else None
                )
            self.backend.save_locked(lead)
            return dict(lead)

    def append_transcript(self, lead_id, segment):
        entry = {
            "id": str(segment.get("id", "")),
            "timestamp": str(segment.get("timestamp", "")),
            "speaker": str(segment.get("speaker", "")),
            "text": str(segment.get("text", "")).strip(),
        }
        if not entry["text"] or entry["speaker"] not in ("Agent", "Prospect"):
            raise ValueError("A transcript segment needs text and a known speaker.")
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            transcript = lead.setdefault("transcript", [])
            if entry["id"] and any(item.get("id") == entry["id"] for item in transcript):
                return dict(lead)
            transcript.append(entry)
            transcript.sort(key=lambda item: item.get("timestamp", ""))
            self.backend.save_locked(lead)
            return dict(lead)

    def append_call_log(self, lead_id, entry, replace_id=None):
        record = {
            "id": str(entry.get("id") or ""),
            "started_at": str(entry.get("started_at") or ""),
            "ended_at": str(entry.get("ended_at") or ""),
            "caller_id": str(entry.get("caller_id") or ""),
            "answered_by": str(entry.get("answered_by") or ""),
            "duration_seconds": int(entry.get("duration_seconds") or 0),
            "transcript_lines": int(entry.get("transcript_lines") or 0),
            # None means unknown, the value older entries have.
            "connected": entry["connected"] if isinstance(entry.get("connected"), bool) else None,
            "outcome": entry.get("outcome") if entry.get("outcome") in CALL_OUTCOME_KEYS else None,
        }
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            log = lead.setdefault("call_log", [])
            if replace_id:
                replaced = [item for item in log if item.get("id") == str(replace_id)]
                # A tag put on the dial-time entry survives the entry that replaces it.
                record["outcome"] = record["outcome"] or next((item.get("outcome") for item in replaced if item.get("outcome")), None)
                log[:] = [item for item in log if item.get("id") != str(replace_id)]
            if record["id"] and any(item.get("id") == record["id"] for item in log):
                return dict(lead)
            log.append(record)
            apply_dial_cap_to_lead(lead)
            self.backend.save_locked(lead)
            return dict(lead)

    def set_call_outcome(self, lead_id, call_ids, outcome):
        """Tag the call-log entry stored under any of call_ids. Returns False when no entry has been written yet."""
        if outcome not in CALL_OUTCOME_KEYS:
            raise ValueError("Unknown call outcome")
        wanted = {str(item) for item in call_ids if item}
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            entries = [item for item in lead.get("call_log") or [] if item.get("id") in wanted]
            if not entries:
                return False
            for item in entries:
                item["outcome"] = outcome
            self.backend.save_locked(lead)
            return True

    def set_booked_at(self, lead_id, booked_at, replace_existing=False):
        """Date a booked prospect that has no booking date. A dated booking is never moved,
        unless the caller just stamped it itself (replace_existing)."""
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            if lead.get("status") != "booked":
                raise ValueError("Mark the prospect booked before dating the booking.")
            if lead.get("booked_at") and not replace_existing:
                raise ValueError("That booking already has a date and is counted.")
            lead["booked_at"] = booked_at
            self.backend.save_locked(lead)
            return dict(lead)


def _copy_of(leads, lead_id):
    lead = next((item for item in leads if item["id"] == lead_id), None)
    if lead is None:
        raise KeyError("Prospect not found")
    return deepcopy(lead)


def post_lead(request, data):
    lead = request.account.crm.add_lead(data)
    request.send_json(200, {"lead": lead, "state": request.ctx.state()})


def post_fields(request, data):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/fields"))
    lead = request.account.crm.update_fields(lead_id, data)
    request.send_json(200, {"lead": lead, "state": request.ctx.state()})


def post_import(request, data):
    result = request.account.crm.add_csv(data)
    try:
        state = request.ctx.state()
    except Exception as exc:
        request.ctx.log(f"Imported CSV but could not refresh state: {exc}", "error")
        state = {"leads": request.account.crm.snapshot()}
    request.send_json(200, {"import": result, "state": state})


def get_export(request):
    try:
        content = request.account.crm.csv_bytes()
        request.send_bytes(200, content, "text/csv; charset=utf-8", {
            "Content-Disposition": "attachment; filename=crm-export.csv",
        })
    except OSError as exc:
        request.report_storage_error(exc)


def delete_lead(request):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/"))
    try:
        request.account.crm.remove(lead_id)
        request.send_json(200, request.ctx.state())
    except KeyError as exc:
        request._trace_error = str(exc)
        request.send_json(404, {"error": str(exc)})
    except OSError as exc:
        request._trace_error = str(exc)
        request.send_json(500, {"error": f"Could not persist data: {exc}"})


ROUTES = [
    ("POST", "/api/leads", post_lead, "POST"),
    ("POST", "/api/leads/{id}/fields", post_fields, "POST"),
    ("POST", "/api/import", post_import, "POST"),
    ("GET", "/api/export.csv", get_export, "GET reads"),
    ("DELETE", "/api/leads/{id}", delete_lead, "DELETE"),
]
