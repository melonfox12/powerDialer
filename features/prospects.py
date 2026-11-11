"""Prospect rules shared by the local and Supabase backends."""

import json
import urllib.parse
from copy import deepcopy
from datetime import datetime, timedelta

from features._prospects.backend_local import LocalBackend
from features._prospects.backend_supabase import SupabaseBackend
from features._prospects.dial_archive import is_dial_archive_storage_lead
from features._prospects.dial_records import is_dial_records_storage_lead
from features._prospects.csv_export import csv_bytes_for
from features._prospects.csv_import import apply_pitch_segment_from_fields, parse_csv, update_lead_fields
from shared.dial_policy import (
    apply_static_callback_status,
    apply_total_dials_callback_status,
    apply_callback_timer_migration_to_lead,
    apply_dial_cap_to_lead,
    dial_cap_reached,
    lead_has_live_contact,
    lead_ids_with_dial_on_local_date,
    repair_dial_status_for_lead,
)
from shared.config import read_env, write_env
from shared.infra import utc_now
from shared.pipeline_config import (
    LOCKED_PIPELINE_KEYS,
    merge_pipeline_steps,
    migrate_leads_pipeline_keys,
    parse_custom_pipeline_steps_json,
    validate_pipeline_tail_payload,
)
from shared.dial_policy import agent_reservation_blocks_other_apps, clear_agent_reservation_fields
from shared.vocabulary import (
    AGENT_RESERVED_ID_FIELD,
    AGENT_RESERVED_NAME_FIELD,
    AGENT_USE_STATUS,
    CALL_OUTCOME_KEYS,
    DEFAULT_BUSINESS_TYPE,
    MANUAL_CALLBACK_HOURS,
    NEVER_DIAL_STATUSES,
    NOV5_2026_STATIC_CALLBACK_DATE,
    PIPELINE_DIALED_STEP,
    PIPELINE_FIRST_STEP,
    PIPELINE_SEND_INFO_STEP,
    STATUS_KEYS,
    agent_use_status_text,
    canonical_status,
    parse_prospect_status,
    pipeline_step_to_status,
)


# Statuses whose pipeline column is derived from CRM status (Dialed / Contacted / tail = Qualified).
PIPELINE_FOLLOW_STATUSES = frozenset({"dialed", "contact_engaged", "qualified"})


class ProspectStore:
    def __init__(self, path=None, *, client=None, user_id=None):
        if client is not None:
            self.backend = SupabaseBackend(client, user_id)
        else:
            self.backend = LocalBackend(path)
        self._pipeline_steps = merge_pipeline_steps([])
        self._pipeline_step_keys = frozenset(s["key"] for s in self._pipeline_steps)
        self.pipeline_revision = 0
        self.migrate_callback_timers_to_two_hours()

    def set_pipeline_schema(self, steps, *, migrate=False, previous_keys=None):
        """Replace active pipeline steps (full ordered list including Dialed + Contacted (engaged) (call_1))."""
        steps = [dict(s) for s in (steps or [])]
        if len(steps) < 2:
            raise ValueError("Pipeline must include Dialed and Contacted (engaged) (call_1).")
        if steps[0]["key"] != PIPELINE_DIALED_STEP or steps[1]["key"] != PIPELINE_SEND_INFO_STEP:
            raise ValueError("First columns must be Dialed then Contacted (engaged) (call_1).")
        for item in steps[:2]:
            try:
                wh = int(item.get("wait_hours") or 0)
            except (TypeError, ValueError):
                wh = -1
            if wh != 0:
                raise ValueError("Dialed and Contacted (engaged) must use zero wait hours.")
        old_keys = frozenset(previous_keys) if previous_keys is not None else frozenset(self._pipeline_step_keys)
        old_snapshot = [dict(s) for s in self._pipeline_steps]
        key_list = [str(s["key"]).strip() for s in steps]
        if len(key_list) != len(set(key_list)):
            raise ValueError("Pipeline step keys must be unique.")
        new_keys_set = frozenset(key_list)
        self._pipeline_steps = steps
        self._pipeline_step_keys = new_keys_set
        touched_count = 0
        if migrate and old_keys != new_keys_set:
            with self.lock:
                leads = self.backend.leads_locked()
                self.backend.expire_locked(leads)
                touched = migrate_leads_pipeline_keys(
                    leads, old_keys, new_keys_set, PIPELINE_SEND_INFO_STEP, PIPELINE_DIALED_STEP,
                )
                for lead_id in touched:
                    lead = _copy_of(leads, lead_id)
                    self.backend.save_locked(lead)
                touched_count = len(touched)
        if old_snapshot != [dict(s) for s in steps] or touched_count:
            self.pipeline_revision += 1
            self.backend.bump_revision()
        return touched_count

    def pipeline_steps_for_catalog(self):
        return [dict(s) for s in self._pipeline_steps]

    def apply_pipeline_tail_from_settings(self, raw_json, *, migrate=False, previous_keys=None):
        """Parse PIPELINE_CUSTOM_STEPS_JSON and merge with locked head; optionally remap CRM."""
        custom, err = parse_custom_pipeline_steps_json(raw_json or "")
        if err:
            raise ValueError(err)
        merged = merge_pipeline_steps(custom)
        return self.set_pipeline_schema(merged, migrate=migrate, previous_keys=previous_keys)

    def remap_pipeline_after_deletion(self, old_keys):
        """After removing steps, move prospects off deleted keys (no extra validation)."""
        new_keys = frozenset(s["key"] for s in self._pipeline_steps)
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            touched = migrate_leads_pipeline_keys(
                leads, frozenset(old_keys), new_keys, PIPELINE_SEND_INFO_STEP, PIPELINE_DIALED_STEP,
            )
            for lead_id in touched:
                lead = _copy_of(leads, lead_id)
                self.backend.save_locked(lead)
        if touched:
            self.pipeline_revision += 1
        return len(touched)

    def sync_pipeline_from_account_values(self, account_values, *, migrate=False):
        """Load PIPELINE_CUSTOM_STEPS_JSON from merged env + account dict."""
        raw = ""
        if account_values:
            raw = str(account_values.get("PIPELINE_CUSTOM_STEPS_JSON") or "").strip()
        prev = frozenset(self._pipeline_step_keys)
        return self.apply_pipeline_tail_from_settings(raw, migrate=migrate, previous_keys=prev)

    def sync_pipeline_from_merged_values(self, before, after, *, migrate_if_steps_removed=True):
        """Sync when settings merge changes; migrate if a custom step key was removed."""
        raw_before = str((before or {}).get("PIPELINE_CUSTOM_STEPS_JSON") or "").strip()
        raw_after = str((after or {}).get("PIPELINE_CUSTOM_STEPS_JSON") or "").strip()
        if raw_before == raw_after:
            return 0
        custom_before, err_b = parse_custom_pipeline_steps_json(raw_before)
        if err_b:
            custom_before = []
        custom_after, err_a = parse_custom_pipeline_steps_json(raw_after)
        if err_a:
            raise ValueError(err_a)
        keys_before = {s["key"] for s in merge_pipeline_steps(custom_before)}
        keys_after = {s["key"] for s in merge_pipeline_steps(custom_after)}
        removed = keys_before - keys_after - LOCKED_PIPELINE_KEYS
        migrate = migrate_if_steps_removed and bool(removed)
        return self.apply_pipeline_tail_from_settings(raw_after, migrate=migrate)

    def set_pipeline_tail(self, tail_steps, *, migrate_leads=False):
        """Replace configurable tail (after Contacted (engaged)). Dialed + call_1 stay fixed."""
        normalized, err = validate_pipeline_tail_payload(tail_steps)
        if err:
            raise ValueError(err)
        for item in normalized:
            if item["key"] in LOCKED_PIPELINE_KEYS:
                raise ValueError("Cannot redefine Dialed or Contacted (engaged) (call_1) in the custom list.")
        merged = merge_pipeline_steps(normalized)
        prev = frozenset(self._pipeline_step_keys)
        return self.set_pipeline_schema(merged, migrate=migrate_leads, previous_keys=prev)

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
        leads = [
            lead for lead in self.backend.snapshot()
            if not is_dial_archive_storage_lead(lead) and not is_dial_records_storage_lead(lead)
        ]
        for lead in leads:
            lead["status"] = canonical_status(lead.get("status"))
            if not str(lead.get("business_type") or "").strip():
                lead["business_type"] = DEFAULT_BUSINESS_TYPE
            apply_pitch_segment_from_fields(lead)
        return leads

    def repair_dial_statuses(self):
        """Undo wrongful closed-by-cap statuses and align dial-cap classification."""
        counts = {"to_new": 0, "to_closed": 0}
        for lead in self.snapshot():
            next_status = repair_dial_status_for_lead(lead)
            if not next_status:
                continue
            self.set_status(lead["id"], next_status, repair=True)
            if next_status == "new":
                counts["to_new"] += 1
            else:
                counts["to_closed"] += 1
        return counts

    def migrate_callback_timers_to_two_hours(self):
        """Shift legacy 48-hour callback deadlines forward once per prospect."""
        now = utc_now()
        shifted = 0
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            for lead in leads:
                if apply_callback_timer_migration_to_lead(lead, now):
                    self.backend.save_locked(lead)
                    shifted += 1
        return shifted

    def enforce_dial_caps(self, *, repair_misclassified=False):
        """Backfill closed at the dial cap. Repair runs only when requested (Scan CRM)."""
        repair = self.repair_dial_statuses() if repair_misclassified else {"to_new": 0, "to_closed": 0}
        capped = 0
        for lead in self.snapshot():
            if not dial_cap_reached(lead):
                continue
            if lead_has_live_contact(lead):
                continue
            if canonical_status(lead.get("status")) in NEVER_DIAL_STATUSES:
                continue
            self.set_status(lead["id"], "closed")
            capped += 1
        return {**repair, "capped": capped}

    def timezone_groups(self, leads=None):
        return self.backend.timezone_groups(leads)

    def csv_bytes(self):
        return self.backend.csv_bytes()

    def add_lead(self, payload):
        lead = self.backend.add_lead(payload)
        if canonical_status(lead.get("status")) == "contact_engaged":
            lead = self.set_pipeline_step(lead["id"], PIPELINE_SEND_INFO_STEP)
        return lead

    def _pipeline_step_for_status(self, status):
        if status == "dialed":
            return PIPELINE_DIALED_STEP
        if status == "contact_engaged":
            return PIPELINE_SEND_INFO_STEP
        if status == "qualified":
            for row in self._pipeline_steps:
                if row["key"] not in LOCKED_PIPELINE_KEYS:
                    return row["key"]
            return PIPELINE_SEND_INFO_STEP
        return None

    def _sync_pipeline_from_status(self, lead, status, changed_at):
        if status not in PIPELINE_FOLLOW_STATUSES:
            return
        step = self._pipeline_step_for_status(status)
        if not step:
            return
        previous = str(lead.get("pipeline_step") or "").strip()
        if previous != step:
            lead.setdefault("pipeline_history", []).append({
                "step": step,
                "entered_at": changed_at,
            })
        lead["pipeline_step"] = step
        lead["pipeline_step_entered_at"] = changed_at

    def update_fields(self, lead_id, payload):
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            others = (item.get("phone") for item in leads if item["id"] != lead_id)
            update_lead_fields(lead, payload, others)
            self.backend.save_locked(lead)
            return dict(lead)

    def set_pipeline_step(self, lead_id, step):
        step = str(step or "").strip()
        if step not in self._pipeline_step_keys:
            raise ValueError("Unknown pipeline step.")
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            if canonical_status(lead.get("status")) not in PIPELINE_FOLLOW_STATUSES:
                raise ValueError("This prospect status cannot be moved on the pipeline board.")
            previous = str(lead.get("pipeline_step") or "").strip()
            entered_at = utc_now().isoformat()
            if previous != step:
                lead.setdefault("pipeline_history", []).append({
                    "step": step,
                    "entered_at": entered_at,
                })
            lead["pipeline_step"] = step
            lead["pipeline_step_entered_at"] = entered_at
            desired = pipeline_step_to_status(step)
            if canonical_status(lead.get("status")) != desired:
                prev_s = canonical_status(lead.get("status"))
                lead.setdefault("status_history", []).append({
                    "from_status": prev_s,
                    "to_status": desired,
                    "changed_at": entered_at,
                })
                lead["status"] = desired
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

    def set_status(self, lead_id, status, scheduled_until=None, *, repair=False, agent_writer_id=None):
        status = parse_prospect_status(status)
        if status not in STATUS_KEYS:
            raise ValueError("Unknown prospect status")
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            lead = _copy_of(leads, lead_id)
            if agent_reservation_blocks_other_apps(lead, agent_writer_id):
                raise ValueError(f"{agent_use_status_text(lead)} — reserved for an AI agent.")
            previous = canonical_status(lead.get("status"))
            changed_at = utc_now().isoformat()
            if previous != status:
                lead.setdefault("status_history", []).append({
                    "from_status": previous,
                    "to_status": status,
                    "changed_at": changed_at,
                })
            lead["status"] = status
            if status == AGENT_USE_STATUS:
                lead["scheduled_until"] = None
            if status in PIPELINE_FOLLOW_STATUSES:
                self._sync_pipeline_from_status(lead, status, changed_at)
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
                    (utc_now() + timedelta(hours=MANUAL_CALLBACK_HOURS)).isoformat() if status == "dialed" else None
                )
            self.backend.save_locked(lead)
            return dict(lead)

    def reserve_for_agent(self, lead_id, agent_id, agent_name):
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            if agent_reservation_blocks_other_apps(lead):
                raise ValueError(f"{agent_use_status_text(lead)} — already reserved.")
            lead[AGENT_RESERVED_NAME_FIELD] = str(agent_name or "").strip()
            lead[AGENT_RESERVED_ID_FIELD] = str(agent_id or "").strip()
            fields = lead.setdefault("fields", {})
            fields[AGENT_RESERVED_NAME_FIELD] = lead[AGENT_RESERVED_NAME_FIELD]
            fields[AGENT_RESERVED_ID_FIELD] = lead[AGENT_RESERVED_ID_FIELD]
            previous = canonical_status(lead.get("status"))
            changed_at = utc_now().isoformat()
            if previous != AGENT_USE_STATUS:
                lead.setdefault("status_history", []).append({
                    "from_status": previous,
                    "to_status": AGENT_USE_STATUS,
                    "changed_at": changed_at,
                })
            lead["status"] = AGENT_USE_STATUS
            lead["scheduled_until"] = None
            self.backend.save_locked(lead)
            return dict(lead)

    def agent_finalize_status(self, lead_id, status, *, agent_id=None):
        status = parse_prospect_status(status)
        if status not in STATUS_KEYS or status == AGENT_USE_STATUS:
            raise ValueError("Invalid agent status update")
        with self.lock:
            leads = self.backend.leads_locked()
            lead = _copy_of(leads, lead_id)
            if agent_reservation_blocks_other_apps(lead, agent_id):
                raise ValueError(f"{agent_use_status_text(lead)} — reserved by another agent.")
            clear_agent_reservation_fields(lead)
            previous = canonical_status(lead.get("status"))
            changed_at = utc_now().isoformat()
            if previous != status:
                lead.setdefault("status_history", []).append({
                    "from_status": previous,
                    "to_status": status,
                    "changed_at": changed_at,
                })
            lead["status"] = status
            if status == "dialed":
                lead["scheduled_until"] = None
            elif status != "dialed":
                lead["scheduled_until"] = None
            if status in PIPELINE_FOLLOW_STATUSES:
                self._sync_pipeline_from_status(lead, status, changed_at)
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

    def clear_all_call_logs(self):
        """Remove every call_log row while keeping prospects and transcripts."""
        with self.lock:
            leads = self.backend.leads_locked()
            for lead in leads:
                if lead.get("call_log"):
                    lead["call_log"] = []
                    self.backend.save_locked(lead)

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
            apply_total_dials_callback_status(lead, record)
            apply_dial_cap_to_lead(lead)
            self.backend.save_locked(lead)
            return dict(lead)

    def repair_total_dials_callbacks(self):
        """Fix prospects still marked New while they have Total dials rows."""
        updated = 0
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            for lead in leads:
                if not lead.get("call_log"):
                    continue
                if canonical_status(lead.get("status")) != "new":
                    continue
                patched = _copy_of(leads, lead["id"])
                if apply_total_dials_callback_status(patched):
                    self.backend.save_locked(patched)
                    updated += 1
        return updated

    def migrate_nov5_2026_static_callbacks(self, archived_rows=()):
        """One-time: Nov 5 Total dials + New (or timed Callback) → static Callback (pipeline Dialed)."""
        updated = 0
        with self.lock:
            leads = self.backend.leads_locked()
            self.backend.expire_locked(leads)
            dialed_ids = lead_ids_with_dial_on_local_date(
                leads, archived_rows, NOV5_2026_STATIC_CALLBACK_DATE,
            )
            for lead in leads:
                if lead.get("id") not in dialed_ids:
                    continue
                status = canonical_status(lead.get("status"))
                if status == "new":
                    pass
                elif status == "dialed" and lead.get("scheduled_until"):
                    pass
                else:
                    continue
                patched = _copy_of(leads, lead["id"])
                if apply_static_callback_status(patched):
                    self.backend.save_locked(patched)
                    updated += 1
        return updated

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


def post_pipeline_step(request, data):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/pipeline"))
    step = data.get("step", PIPELINE_FIRST_STEP)
    lead = request.account.crm.set_pipeline_step(lead_id, step)
    request.send_json(200, {"lead": lead, "state": request.ctx.state()})


def post_save_pipeline_settings(request, data):
    steps = data.get("steps")
    migrate_leads = bool(data.get("migrate_leads"))
    if not isinstance(steps, list):
        raise ValueError("Expected steps array.")
    dialer = request.account.dialer
    crm = request.account.crm
    json_text = json.dumps(steps, ensure_ascii=False, separators=(",", ":"))
    touched = crm.set_pipeline_tail(steps, migrate_leads=migrate_leads)
    dialer.account_values["PIPELINE_CUSTOM_STEPS_JSON"] = json_text
    if getattr(dialer, "account_user_id", None):
        saver = getattr(dialer, "settings_saver", None)
        if saver:
            saver(dialer)
    else:
        write_env(dialer.env_path, {"PIPELINE_CUSTOM_STEPS_JSON": json_text})
        dialer.account_values.update(read_env(dialer.env_path))
    request.send_json(200, {
        "pipeline_steps": crm.pipeline_steps_for_catalog(),
        "pipeline_revision": crm.pipeline_revision,
        "migrated_leads": touched,
        "state": request.ctx.state(),
    })


def post_import(request, data):
    result = request.account.crm.add_csv(data)
    request.account.dialer.maintain_crm()
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
        crm = request.account.crm
        archive = request.account.dial_archive
        lead = next((item for item in crm.snapshot() if item.get("id") == lead_id), None)
        if lead is None:
            raise KeyError("Prospect not found")
        archive.archive_lead(lead)
        crm.remove(lead_id)
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
    ("POST", "/api/leads/{id}/pipeline", post_pipeline_step, "POST"),
    ("POST", "/api/pipeline/settings", post_save_pipeline_settings, "POST"),
    ("POST", "/api/import", post_import, "POST"),
    ("GET", "/api/export.csv", get_export, "GET reads"),
    ("DELETE", "/api/leads/{id}", delete_lead, "DELETE"),
]
