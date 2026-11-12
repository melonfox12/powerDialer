"""Dialer entry. Part import order, low to high:

twilio → state → rules → calls → projection → slots → timing → queue → _call_events → call_events → outcomes.

slots imports calls and rules. timing imports slots and projection. queue imports calls, then slots, then timing. call_events imports pickup, transcript, then ended. projection imports calls and does not import anything above it. Nothing in features/_dialer imports this module. Parts read credentials and preferences through read_values and read_settings.
"""

import urllib.parse
from datetime import date

from features import ai_agents, ai_agent_playbook, settings as settings_feature
from features._dialer import call_events, outcomes, projection, queue, twilio
from features._dialer._call_events import ended, pickup, transcript
from features._dialer import calls, rules, slots, timing
from features._dialer.state import DialerState
from features._dialer.twilio import TokenIndex, TwilioError

__all__ = ["Dialer", "ROUTES", "TokenIndex", "TwilioError"]


class Dialer(DialerState):
    def read_values(self):
        return settings_feature.values(self.env_path, self.account_values, signed_in=bool(self.account_user_id))

    def read_settings(self):
        current = self.read_values()
        return {**current, **settings_feature.preferences(current)}

    def public_state(self, include_leads=False):
        return projection.public_state(self, include_leads=include_leads)

    def leads_catalog(self):
        return projection.leads_catalog(self)

    def maintain_crm(self):
        return queue.maintain_crm(self)

    def live_state(self):
        return projection.live_state(self)

    def set_timezone_filter(self, timezone):
        return queue.set_timezone_filter(self, timezone)

    def set_pool_filters(self, timezone=None, pool_status=None, business_type=None):
        return queue.set_pool_filters(
            self, timezone=timezone, pool_status=pool_status, business_type=business_type,
        )

    def set_caller_id_group(self, key):
        return queue.set_caller_id_group(self, key)

    def scan_crm(self):
        return queue.scan_crm(self)

    def backfill_new_dial_callbacks(self):
        count = queue.repair_total_dials_callbacks(self)
        if count:
            noun = "prospect" if count == 1 else "prospects"
            self.record_activity(
                f"One-time fix: 2-hour callback on {count} {noun} still New in the current dial log",
                "web",
            )
        return count

    def start(self, priority_lead_id=None):
        return queue.start(self, priority_lead_id)

    def start_ai_agent(self, agent_id):
        return ai_agents.start_agent(self, agent_id)

    def stop_ai_agent(self, agent_id):
        return ai_agents.stop_agent(self, agent_id)

    def boot_ai_agent_pool(self, agent_id):
        return ai_agents.boot_agent_pool(self, agent_id)

    def release_ai_agent_pool(self, agent_id):
        return ai_agents.release_agent_pool(self, agent_id)

    def ai_agent_playbook(self, agent_id):
        name = ai_agents._agent_name(agent_id)
        return ai_agent_playbook.get_playbook(self, agent_id, name)

    def save_ai_agent_playbook(self, agent_id, payload):
        name = ai_agents._agent_name(agent_id)
        return ai_agent_playbook.save_playbook(self, agent_id, payload, name)

    def rejoin_browser_voice(self):
        return queue.rejoin_browser_voice(self)

    def _new_call(self, kind, lead):
        call = calls._new_call(self, kind, lead)
        rules._flush_metrics(self)
        return call

    def dial_lead(self, lead_id):
        return queue.dial_lead(self, lead_id)

    def pause(self):
        return queue.pause(self)

    def stop(self):
        return queue.stop(self)

    def fill_slots(self):
        return slots.fill_slots(self)

    def advance_now(self):
        return timing.advance_now(self)

    def handle_webhook(self, token, action, params):
        return call_events.handle_webhook(self, token, action, params)

    def handle_client_voice(self, params):
        return call_events.handle_client_voice(self, params)

    def hangup_active(self):
        return call_events.hangup_active(self)

    def skip_active(self):
        return call_events.skip_active(self)

    def pass_next(self, lead_id):
        return queue.pass_next(self, lead_id)

    def _pickup(self, call):
        return pickup._pickup(self, call)

    def _machine_result(self, call, params):
        return pickup._machine_result(self, call, params)

    def _transcription_event(self, call, params):
        return transcript._transcription_event(self, call, params)

    def _call_ended(self, call, params):
        return ended._call_ended(self, call, params)

    def update_status(self, lead_id, status=None, scheduled_until=None, disposition=None, crm_only=False):
        return outcomes.update_status(self, lead_id, status, scheduled_until, disposition, crm_only)

    def tag_call(self, lead_id, outcome):
        return outcomes.tag_call(self, lead_id, outcome)

    def log_booking(self, lead_id, booked_at):
        return outcomes.log_booking(self, lead_id, booked_at)

    def validate_webhook(self, url, signature, params):
        return twilio.validate_webhook(self, url, signature, params)

    def voice_access_token(self):
        return twilio.voice_access_token(self)

    def settings_state(self):
        return settings_feature.settings_state(
            self.env_path,
            self.account_values,
            getattr(self, "storage_name", "local JSON files"),
            getattr(self, "account_email", ""),
            signed_in=bool(self.account_user_id),
        )

    def save_settings(self, data):
        save_remote = None
        saver = getattr(self, "settings_saver", None)
        if saver:
            def save_remote(_stored, saver=saver):
                saver(self)
        parsed = settings_feature.save_settings(
            self.env_path, self.account_values, self.account_user_id, data, save_remote,
        )
        with self.lock:
            self.settings.update(parsed)
        return self.settings_state()

    def save_goal(self, data):
        save_remote = None
        saver = getattr(self, "settings_saver", None)
        if saver:
            def save_remote(_stored, saver=saver):
                saver(self)
        parsed = settings_feature.save_goal(
            self.env_path, self.account_values, self.account_user_id, data,
            date.today(), save_remote,
        )
        with self.lock:
            self.settings.update(parsed)
        return settings_feature.daily_goal(parsed)


def _maybe_run_nov5_static_callback_migration(request):
    dialer = request.account.dialer
    if getattr(dialer, "_nov5_static_callback_migration_checked", False):
        return
    dialer._nov5_static_callback_migration_checked = True
    archive = getattr(dialer, "dial_archive", None) or request.account.dial_archive
    queue.ensure_nov5_static_callback_migration(dialer, archive)


def get_state(request):
    try:
        _maybe_run_nov5_static_callback_migration(request)
        request.send_json(200, request.account.dialer.public_state(include_leads=False))
    except OSError as exc:
        request.report_storage_error(exc)


def get_leads(request):
    try:
        _maybe_run_nov5_static_callback_migration(request)
        request.send_json(200, request.account.dialer.leads_catalog())
    except OSError as exc:
        request.report_storage_error(exc)


def get_live(request):
    try:
        request.send_json(200, request.account.dialer.live_state())
    except OSError as exc:
        request.report_storage_error(exc)


def get_voice_token(request):
    try:
        request.send_json(200, {"token": request.account.dialer.voice_access_token()})
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})


def post_timezone(request, data):
    timezone = data.get("timezone") if "timezone" in data else None
    pool_status = data.get("pool_status") if "pool_status" in data else None
    business_type = data.get("business_type") if "business_type" in data else None
    try:
        request.send_json(200, request.account.dialer.set_pool_filters(
            timezone=timezone, pool_status=pool_status, business_type=business_type,
        ))
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})


def post_caller_id_group(request, data):
    try:
        request.send_json(200, request.account.dialer.set_caller_id_group(data.get("caller_id_group")))
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})


def post_start(request):
    request.send_json(200, request.account.dialer.start())


def post_voice_rejoin(request):
    try:
        request.send_json(200, request.account.dialer.rejoin_browser_voice())
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})


def post_pause(request):
    request.send_json(200, request.account.dialer.pause())


def post_stop(request):
    request.send_json(200, request.account.dialer.stop())


def post_hangup(request):
    request.send_json(200, request.account.dialer.hangup_active())


def post_skip(request):
    request.send_json(200, request.account.dialer.skip_active())


def post_pass_next(request, data):
    request.send_json(200, request.account.dialer.pass_next(data.get("id")))


def post_advance(request):
    request.send_json(200, request.account.dialer.advance_now())


def post_scan_crm(request):
    request.send_json(200, request.account.dialer.scan_crm())


def post_backfill_new_dial_callbacks(request):
    count = request.account.dialer.backfill_new_dial_callbacks()
    try:
        state = request.ctx.state()
    except OSError as exc:
        request.ctx.log(f"Callbacks backfilled but state refresh failed: {exc}", "error")
        state = request.account.dialer.public_state(include_leads=False)
    request.send_json(200, {"updated": count, "state": state})


def post_backfill_nov5_static_callbacks(request):
    dialer = request.account.dialer
    archive = getattr(dialer, "dial_archive", None) or request.account.dial_archive
    count = queue.ensure_nov5_static_callback_migration(dialer, archive, force=True)
    try:
        state = request.ctx.state()
    except OSError as exc:
        request.ctx.log(f"Nov 5 backfill finished but state refresh failed: {exc}", "error")
        state = dialer.public_state(include_leads=False)
    request.send_json(200, {"updated": count, "state": state})


def post_dial(request):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/dial"))
    request.send_json(200, request.account.dialer.dial_lead(lead_id))


def post_status(request, data):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/status"))
    dialer = request.account.dialer
    dialer.update_status(
        lead_id, data.get("status"), data.get("scheduled_until"), data.get("disposition"),
        crm_only=bool(data.get("crm_only")),
    )
    state = dialer.public_state(include_leads=False)
    lead = next((item for item in dialer.crm.snapshot() if item.get("id") == lead_id), None)
    if lead is None:
        raise KeyError("Prospect not found")
    request.send_json(200, {"lead": lead, "state": state})


def get_dials_export(request):
    from features._prospects.dials_csv_export import dials_csv_bytes_for

    try:
        archive = request.account.dial_archive.snapshot()
        content = dials_csv_bytes_for(request.account.crm.snapshot(), archive)
        request.send_bytes(200, content, "text/csv; charset=utf-8", {
            "Content-Disposition": "attachment; filename=total-dials-export.csv",
        })
    except OSError as exc:
        request.report_storage_error(exc)


def post_dials_import(request, data):
    try:
        result = request.account.dial_archive.import_csv_bytes(data, crm=request.account.crm)
        request.send_json(200, {"import": result, "state": request.ctx.state()})
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})
    except OSError as exc:
        request.report_storage_error(exc)


def post_dials_record_snapshot(request, data):
    from features._prospects.dial_records import snapshot_active_dials

    try:
        saved = snapshot_active_dials(
            request.account.crm,
            request.account.dial_archive,
            request.account.dial_records,
            title=(data or {}).get("title"),
        )
        request.send_json(200, {"record": saved, "state": request.ctx.state()})
    except ValueError as exc:
        request._trace_error = str(exc)
        request.send_json(400, {"error": str(exc)})
    except OSError as exc:
        request.report_storage_error(exc)


def get_dials_record(request):
    record_id = urllib.parse.unquote(
        request._trace_path.removeprefix("/api/dials/records/").strip("/"),
    )
    record = request.account.dial_records.get_record(record_id)
    if record is None:
        request._trace_error = "Record not found"
        request.send_json(404, {"error": "Record not found"})
        return
    request.send_json(200, {"record": record})


def post_call_outcome(request, data):
    lead_id = urllib.parse.unquote(request._trace_path.removeprefix("/api/leads/").removesuffix("/call-outcome"))
    dialer = request.account.dialer
    lead = dialer.tag_call(lead_id, data.get("outcome"))
    request.send_json(200, {"lead": lead, "state": dialer.public_state(include_leads=False)})


def get_ai_agents(request):
    request.send_json(200, ai_agents.agents_public_view(request.account.dialer))


def post_ai_agent_boot(request, data):
    agent_id = data.get("agent_id") or urllib.parse.unquote(
        request._trace_path.removeprefix("/api/ai-agents/").removesuffix("/boot").strip("/"),
    )
    dialer = request.account.dialer
    result = dialer.boot_ai_agent_pool(agent_id)
    request.send_json(200, {**result, "state": dialer.public_state(include_leads=False)})


def post_ai_agent_start(request, data):
    agent_id = data.get("agent_id") or urllib.parse.unquote(
        request._trace_path.removeprefix("/api/ai-agents/").removesuffix("/start").strip("/"),
    )
    dialer = request.account.dialer
    view = dialer.start_ai_agent(agent_id)
    request.send_json(200, view)


def post_ai_agent_stop(request, data):
    agent_id = data.get("agent_id") or urllib.parse.unquote(
        request._trace_path.removeprefix("/api/ai-agents/").removesuffix("/stop").strip("/"),
    )
    dialer = request.account.dialer
    view = dialer.stop_ai_agent(agent_id)
    request.send_json(200, view)


def post_ai_agent_release(request, data):
    agent_id = data.get("agent_id") or urllib.parse.unquote(
        request._trace_path.removeprefix("/api/ai-agents/").removesuffix("/release-pool").strip("/"),
    )
    dialer = request.account.dialer
    result = dialer.release_ai_agent_pool(agent_id)
    request.send_json(200, {**result, "state": dialer.public_state(include_leads=False)})


def get_ai_agent_playbook(request):
    query = urllib.parse.parse_qs(urllib.parse.urlsplit(request.path).query)
    agent_id = (query.get("agent_id") or query.get("agentId") or [""])[-1]
    dialer = request.account.dialer
    playbook = dialer.ai_agent_playbook(agent_id)
    request.send_json(200, {"agent_id": str(agent_id).strip(), "playbook": playbook})


def post_ai_agent_playbook(request, data):
    agent_id = data.get("agent_id") or ""
    dialer = request.account.dialer
    playbook = dialer.save_ai_agent_playbook(agent_id, data.get("playbook") or data)
    request.send_json(200, {"agent_id": str(agent_id).strip(), "playbook": playbook})


ROUTES = [
    ("GET", "/api/state", get_state, "GET reads"),
    ("GET", "/api/leads", get_leads, "GET reads"),
    ("GET", "/api/live", get_live, "GET reads"),
    ("GET", "/api/voice-token", get_voice_token, "voice-token"),
    ("POST", "/api/voice/rejoin", post_voice_rejoin, "POST"),
    ("POST", "/api/timezone", post_timezone, "POST"),
    ("POST", "/api/caller-id-group", post_caller_id_group, "POST"),
    ("POST", "/api/start", post_start, "POST"),
    ("POST", "/api/pause", post_pause, "POST"),
    ("POST", "/api/stop", post_stop, "POST"),
    ("POST", "/api/hangup", post_hangup, "POST"),
    ("POST", "/api/skip", post_skip, "POST"),
    ("POST", "/api/next/skip", post_pass_next, "POST"),
    ("POST", "/api/advance", post_advance, "POST"),
    ("POST", "/api/dials/scan", post_scan_crm, "POST"),
    ("POST", "/api/dials/backfill-new-callbacks", post_backfill_new_dial_callbacks, "POST"),
    ("POST", "/api/dials/backfill-nov5-static-callbacks", post_backfill_nov5_static_callbacks, "POST"),
    ("GET", "/api/dials/export.csv", get_dials_export, "GET reads"),
    ("POST", "/api/dials/import", post_dials_import, "POST"),
    ("POST", "/api/dials/records/snapshot", post_dials_record_snapshot, "POST"),
    ("GET", "/api/dials/records/{id}", get_dials_record, "GET reads"),
    ("POST", "/api/leads/{id}/dial", post_dial, "POST"),
    ("POST", "/api/leads/{id}/status", post_status, "POST"),
    ("POST", "/api/leads/{id}/call-outcome", post_call_outcome, "POST"),
    ("GET", "/api/ai-agents", get_ai_agents, "GET reads"),
    ("POST", "/api/ai-agents/boot", post_ai_agent_boot, "POST"),
    ("POST", "/api/ai-agents/start", post_ai_agent_start, "POST"),
    ("POST", "/api/ai-agents/stop", post_ai_agent_stop, "POST"),
    ("POST", "/api/ai-agents/release-pool", post_ai_agent_release, "POST"),
    ("GET", "/api/ai-agents/playbook", get_ai_agent_playbook, "GET reads"),
    ("POST", "/api/ai-agents/playbook", post_ai_agent_playbook, "POST"),
]
