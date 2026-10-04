"""Split specs for turning large Python modules into packages."""

PACKAGES = [
    {
        "file": "crm_store/csv_io.py",
        "package": "crm_store.csv_io",
        "modules": [
            {"name": "fields.py", "funcs": ["_phone", "_timezone", "_review_count", "_choose_dialect", "_read_csv", "_unique_headers"]},
            {"name": "parse.py", "funcs": ["parse_csv"]},
            {"name": "export.py", "funcs": ["csv_bytes_for"]},
        ],
        "init": "from crm_store.csv_io.export import csv_bytes_for\nfrom crm_store.csv_io.parse import parse_csv\n\n__all__ = [\"csv_bytes_for\", \"parse_csv\"]\n",
    },
    {
        "file": "crm_store/leads.py",
        "package": "crm_store.leads",
        "modules": [
            {"name": "storage.py", "class_name": "StorageMixin", "methods": ["__init__", "load", "save", "expire_due", "snapshot", "timezone_groups", "csv_bytes"]},
            {"name": "records.py", "class_name": "RecordMixin", "methods": ["add_csv", "set_status", "append_transcript", "append_call_log", "remove"]},
        ],
        "init": "from crm_store.leads.records import RecordMixin\nfrom crm_store.leads.storage import StorageMixin\n\n\nclass CRMStore(RecordMixin, StorageMixin):\n    pass\n",
    },
    {
        "file": "routes/ui.py",
        "package": "routes.ui",
        "replace_runtime": True,
        "modules": [
            {"name": "account.py", "class_name": "AccountMixin", "methods": ["open_account", "ingest_client_debug", "report_storage_error"]},
            {"name": "read.py", "class_name": "ReadMixin", "methods": ["do_GET"]},
            {"name": "write.py", "class_name": "WriteMixin", "methods": ["do_POST", "do_DELETE"]},
        ],
        "init": (
            "from http.server import BaseHTTPRequestHandler\n\n"
            "from routes.http import HandlerMixin\n"
            "from routes.ui.account import AccountMixin\n"
            "from routes.ui.read import ReadMixin\n"
            "from routes.ui.write import WriteMixin\n\n\n"
            "def make_app_handler(runtime):\n"
            "    class AppHandler(AccountMixin, ReadMixin, WriteMixin, HandlerMixin, BaseHTTPRequestHandler):\n"
            "        pass\n\n"
            "    AppHandler.runtime = runtime\n"
            "    return AppHandler\n"
        ),
    },
    {
        "file": "supabase_store/client.py",
        "package": "supabase_store.client",
        "modules": [
            {"name": "pool.py", "classes": ["_ConnectionPool"]},
            {"name": "keys.py", "assigns": ["METRIC_KEYS", "SETTINGS_ROW_ID", "REMOTE_SETTING_KEYS"]},
            {"name": "session.py", "classes": ["SupabaseClient"]},
        ],
        "init": (
            "from supabase_store.client.keys import METRIC_KEYS, REMOTE_SETTING_KEYS, SETTINGS_ROW_ID\n"
            "from supabase_store.client.pool import _ConnectionPool\n"
            "from supabase_store.client.session import SupabaseClient\n\n"
            "__all__ = [\"METRIC_KEYS\", \"REMOTE_SETTING_KEYS\", \"SETTINGS_ROW_ID\", \"SupabaseClient\", \"_ConnectionPool\"]\n"
        ),
    },
    {
        "file": "supabase_store/leads.py",
        "package": "supabase_store.leads",
        "external": {"METRIC_KEYS": "supabase_store.client"},
        "modules": [
            {"name": "records.py", "class_name": "RecordMixin", "methods": ["__init__", "_scope", "_touch", "_fetch", "_all", "_write", "_expire", "snapshot", "timezone_groups", "csv_bytes"]},
            {"name": "changes.py", "class_name": "ChangeMixin", "methods": ["add_csv", "set_status", "remove"]},
            {"name": "metrics.py", "classes": ["SupabaseMetricsStore"]},
        ],
        "init": (
            "from supabase_store.leads.changes import ChangeMixin\n"
            "from supabase_store.leads.metrics import SupabaseMetricsStore\n"
            "from supabase_store.leads.records import RecordMixin\n"
            "from supabase_store.transcripts import TranscriptMixin\n\n\n"
            "class SupabaseCRMStore(ChangeMixin, RecordMixin, TranscriptMixin):\n"
            "    pass\n"
        ),
    },
    {
        "file": "supabase_store/transcripts.py",
        "package": "supabase_store.transcripts",
        "modules": [
            {"name": "mixin.py", "classes": ["TranscriptMixin"]},
            {"name": "migrate.py", "funcs": ["migrate_local_data"]},
            {"name": "settings_io.py", "funcs": ["load_app_settings", "save_app_settings", "hydrate_env_from_supabase"]},
        ],
        "init": (
            "from supabase_store.transcripts.migrate import migrate_local_data\n"
            "from supabase_store.transcripts.mixin import TranscriptMixin\n"
            "from supabase_store.transcripts.settings_io import hydrate_env_from_supabase, load_app_settings, save_app_settings\n\n"
            "__all__ = [\"TranscriptMixin\", \"hydrate_env_from_supabase\", \"load_app_settings\", \"migrate_local_data\", \"save_app_settings\"]\n"
        ),
    },
    {
        "file": "twilio_calls/client.py",
        "package": "twilio_calls.client",
        "external": {"TWILIO_API": "twilio_calls.settings"},
        "modules": [
            {"name": "http.py", "classes": ["TwilioError"], "funcs": ["twilio_request"]},
            {"name": "phone.py", "funcs": ["normalize_phone", "escape_xml"]},
            {"name": "calls.py", "class_name": "ClientMixin", "methods": ["validate_webhook", "_url", "_next_caller", "_launch_call", "_create_call", "_transfer", "_cancel_call", "_hangup_call"]},
        ],
        "init": (
            "from twilio_calls.client.calls import ClientMixin\n"
            "from twilio_calls.client.http import TwilioError, twilio_request\n"
            "from twilio_calls.client.phone import escape_xml, normalize_phone\n\n"
            "__all__ = [\"ClientMixin\", \"TwilioError\", \"escape_xml\", \"normalize_phone\", \"twilio_request\"]\n"
        ),
    },
    {
        "file": "twilio_calls/settings.py",
        "package": "twilio_calls.settings",
        "modules": [
            {"name": "defaults.py", "assigns": ["TWILIO_API", "DIALER_DEFAULTS"], "funcs": ["_preferences", "read_env", "write_env"]},
            {"name": "mixin.py", "class_name": "SettingsMixin", "methods": ["_values", "settings_state", "save_settings"]},
        ],
        "init": (
            "from twilio_calls.settings.defaults import DIALER_DEFAULTS, TWILIO_API, _preferences, read_env, write_env\n"
            "from twilio_calls.settings.mixin import SettingsMixin\n\n"
            "__all__ = [\"DIALER_DEFAULTS\", \"SettingsMixin\", \"TWILIO_API\", \"_preferences\", \"read_env\", \"write_env\"]\n"
        ),
    },
    {
        "file": "twilio_calls/token.py",
        "package": "twilio_calls.token",
        "modules": [
            {"name": "index.py", "classes": ["TokenIndex"]},
            {"name": "voice.py", "class_name": "VoiceMixin", "methods": ["_watch_token", "_release_tokens", "voice_access_token", "handle_client_voice"]},
            {"name": "start.py", "class_name": "StartMixin", "methods": ["start", "_new_call"]},
        ],
        "init": (
            "from twilio_calls.token.index import TokenIndex\n"
            "from twilio_calls.token.start import StartMixin\n"
            "from twilio_calls.token.voice import VoiceMixin\n\n\n"
            "class TokenMixin(StartMixin, VoiceMixin):\n"
            "    pass\n"
        ),
    },
    {
        "file": "twilio_calls/transcript.py",
        "package": "twilio_calls.transcript",
        "modules": [
            {"name": "live.py", "class_name": "LiveMixin", "methods": ["_live_twiml", "_start_transcription", "_transcription_event"]},
            {"name": "ended.py", "class_name": "EndedMixin", "methods": ["_call_ended", "_agent_call_ended"]},
        ],
        "init": (
            "from twilio_calls.transcript.ended import EndedMixin\n"
            "from twilio_calls.transcript.live import LiveMixin\n\n\n"
            "class TranscriptMixin(EndedMixin, LiveMixin):\n"
            "    pass\n"
        ),
    },
    {
        "file": "twilio_calls/webhooks.py",
        "package": "twilio_calls.webhooks",
        "modules": [
            {"name": "dispatch.py", "class_name": "DispatchMixin", "methods": ["_uuid", "handle_webhook"]},
            {"name": "pickup.py", "class_name": "PickupMixin", "methods": ["_pickup", "_machine_result", "_answer_detection_timeout"]},
            {"name": "live.py", "class_name": "LiveMixin", "methods": ["enter_live_line", "_select_human"]},
        ],
        "init": (
            "from twilio_calls.webhooks.dispatch import DispatchMixin\n"
            "from twilio_calls.webhooks.live import LiveMixin\n"
            "from twilio_calls.webhooks.pickup import PickupMixin\n\n\n"
            "class WebhookMixin(DispatchMixin, PickupMixin, LiveMixin):\n"
            "    pass\n"
        ),
    },
    {
        "file": "twilio_calls/lifecycle.py",
        "package": "twilio_calls.lifecycle",
        "modules": [
            {"name": "outcome.py", "class_name": "OutcomeMixin", "methods": ["live_outcome_lead_id", "choose_outcome", "update_status"]},
            {"name": "queue.py", "class_name": "QueueMixin", "methods": ["_schedule_advance", "_advance_queue", "advance_now", "fill_slots", "_schedule_calling_window_check", "_check_calling_window"]},
            {"name": "controls.py", "class_name": "ControlsMixin", "methods": ["pause", "hangup_active", "skip_active", "stop"]},
        ],
        "init": (
            "from twilio_calls.lifecycle.controls import ControlsMixin\n"
            "from twilio_calls.lifecycle.outcome import OutcomeMixin\n"
            "from twilio_calls.lifecycle.queue import QueueMixin\n\n\n"
            "class LifecycleMixin(ControlsMixin, QueueMixin, OutcomeMixin):\n"
            "    pass\n"
        ),
    },
    {
        "file": "twilio_calls/dialer.py",
        "package": "twilio_calls.dialer",
        "modules": [
            {"name": "core.py", "class_name": "CoreMixin", "methods": ["__init__", "_save_session", "_pool_leads", "set_timezone_filter", "_bump", "record_activity", "live_state"]},
            {"name": "state.py", "class_name": "StateMixin", "methods": ["public_state"]},
        ],
        "init": (
            "from twilio_calls.client import ClientMixin\n"
            "from twilio_calls.dialer.core import CoreMixin\n"
            "from twilio_calls.dialer.state import StateMixin\n"
            "from twilio_calls.lifecycle import LifecycleMixin\n"
            "from twilio_calls.settings import SettingsMixin\n"
            "from twilio_calls.token import TokenMixin\n"
            "from twilio_calls.transcript import TranscriptMixin\n"
            "from twilio_calls.webhooks import WebhookMixin\n\n\n"
            "class TwilioDialer(CoreMixin, StateMixin, SettingsMixin, ClientMixin, TokenMixin, WebhookMixin, TranscriptMixin, LifecycleMixin):\n"
            "    pass\n"
        ),
    },
]
