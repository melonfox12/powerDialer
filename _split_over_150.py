"""One-shot splitter. Deleted after the packages are in place."""

import ast
import os
import re
import shutil
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent

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


def span(node):
    start = node.lineno
    if getattr(node, "decorator_list", None):
        start = node.decorator_list[0].lineno
    return start, node.end_lineno


def used_names(source):
    tree = ast.parse(source)
    found = set()

    class Walk(ast.NodeVisitor):
        def visit_Name(self, node):
            if isinstance(node.ctx, ast.Load):
                found.add(node.id)
            self.generic_visit(node)

    Walk().visit(tree)
    return found


def import_lines(tree, needed):
    lines = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            kept = [alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                    for alias in node.names
                    if (alias.asname or alias.name.split(".")[0]) in needed]
            if kept:
                lines.append("import " + ", ".join(kept))
        elif isinstance(node, ast.ImportFrom):
            module = "." * node.level + (node.module or "")
            kept = []
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound in needed:
                    kept.append(alias.name if alias.asname is None else f"{alias.name} as {alias.asname}")
            if kept:
                lines.append(f"from {module} import " + ", ".join(kept))
    return lines


def slice_text(lines, start, end):
    return "\n".join(lines[start - 1:end]).rstrip() + "\n"


def dedented_methods(lines, nodes):
    chunks = [slice_text(lines, *span(node)).rstrip() for node in nodes]
    body = "\n\n".join(textwrap.dedent(chunk) for chunk in chunks).rstrip() + "\n"
    return textwrap.indent(body, "    ")


def render_module(spec, module, lines, lookup, owners, external):
    pieces = []
    defined_here = set()
    if module.get("assigns"):
        for name in module["assigns"]:
            node = lookup["assigns"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("classes"):
        for name in module["classes"]:
            node = lookup["classes"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("funcs"):
        for name in module["funcs"]:
            node = lookup["funcs"][name]
            pieces.append(slice_text(lines, *span(node)).rstrip())
            defined_here.add(name)
    if module.get("methods"):
        nodes = [lookup["methods"][name] for name in module["methods"]]
        method_body = dedented_methods(lines, nodes)
        if spec.get("replace_runtime"):
            method_body = re.sub(r"\bruntime\b", "self.runtime", method_body)
        pieces.append(f"class {module['class_name']}:\n{method_body}".rstrip())
    source_for_names = "\n\n".join(pieces) + "\n"
    needed = used_names(source_for_names)
    header = import_lines(lookup["tree"], needed)
    for name in sorted(needed):
        if name in defined_here or name in module.get("methods", []):
            continue
        owner = owners.get(name)
        if owner and owner != module["name"]:
            stem = owner[:-3] if owner.endswith(".py") else owner
            header.append(f"from {spec['package']}.{stem} import {name}")
        elif name in external:
            header.append(f"from {external[name]} import {name}")
    body = source_for_names
    if module.get("methods") and spec.get("replace_runtime"):
        body = source_for_names
    text = ("\n".join(header) + ("\n\n" if header else "") + body).rstrip() + "\n"
    return text


def build_lookup(tree):
    lookup = {"tree": tree, "funcs": {}, "assigns": {}, "classes": {}, "methods": {}}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            lookup["funcs"][node.name] = node
            for inner in ast.walk(node):
                if isinstance(inner, ast.ClassDef):
                    for item in inner.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            lookup["methods"][item.name] = item
        elif isinstance(node, ast.ClassDef):
            lookup["classes"][node.name] = node
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    lookup["methods"][item.name] = item
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    lookup["assigns"][target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            lookup["assigns"][node.target.id] = node
    return lookup


def owners_for(spec):
    owners = {}
    for module in spec["modules"]:
        for key in ("funcs", "assigns", "classes"):
            for name in module.get(key, []):
                owners[name] = module["name"]
    return owners


def write_package(spec):
    path = ROOT / spec["file"]
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    lookup = build_lookup(tree)
    owners = owners_for(spec)
    external = spec.get("external", {})
    staging = path.with_name(path.stem + "__next")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    written = {}
    for module in spec["modules"]:
        text = render_module(spec, module, lines, lookup, owners, external)
        ast.parse(text)
        target = staging / module["name"]
        target.write_text(text, encoding="utf-8", newline="\n")
        written[module["name"]] = text.count("\n")
    init = staging / "__init__.py"
    init.write_text(spec["init"], encoding="utf-8", newline="\n")
    ast.parse(spec["init"])
    written["__init__.py"] = spec["init"].count("\n")
    return staging, written


def split_tests(path, fixture_names):
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source)
    lookup = build_lookup(tree)
    test_class = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name.endswith("Tests"))
    methods = [item for item in test_class.body if isinstance(item, ast.FunctionDef)]
    groups = []
    current = []
    current_lines = 0
    for method in methods:
        start, end = span(method)
        size = end - start + 1
        if current and current_lines + size > 100:
            groups.append(current)
            current = []
            current_lines = 0
        current.append(method)
        current_lines += size
    if current:
        groups.append(current)
    package = path.stem
    qual = f"tests.{package}"
    staging = path.with_name(package + "__next")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir()
    owners = {}
    modules = []
    if fixture_names:
        modules.append({"name": "fixtures.py", "funcs": [name for name in fixture_names if name in lookup["funcs"]], "classes": [name for name in fixture_names if name in lookup["classes"]]})
        for name in fixture_names:
            owners[name] = "fixtures.py"
    part_classes = []
    for index, group in enumerate(groups, start=1):
        name = f"part_{index}.py"
        class_name = f"Part{index}"
        modules.append({"name": name, "class_name": class_name, "methods": [method.name for method in group]})
        part_classes.append((name, class_name))
    spec = {"package": qual, "file": str(path.relative_to(ROOT)).replace("\\", "/"), "modules": modules, "external": {}, "replace_runtime": False}
    # methods live on the test class, so point lookup methods at that class
    written = {}
    for module in modules:
        text = render_module(spec, module, lines, lookup, owners, {})
        ast.parse(text)
        (staging / module["name"]).write_text(text, encoding="utf-8", newline="\n")
        written[module["name"]] = text.count("\n")
    imports = "\n".join(f"from {qual}.{name[:-3]} import {class_name}" for name, class_name in part_classes)
    bases = ", ".join(class_name for _, class_name in part_classes)
    init = f"import unittest\n\n{imports}\n\n\nclass {test_class.name}({bases}, unittest.TestCase):\n    pass\n"
    ast.parse(init)
    (staging / "__init__.py").write_text(init, encoding="utf-8", newline="\n")
    written["__init__.py"] = init.count("\n")
    return staging, written


def commit(staging, original):
    original.unlink()
    destination = original.with_suffix("")
    if destination.exists():
        raise SystemExit(f"Refusing to replace {destination}")
    staging.rename(destination)


def main():
    staged = []
    too_long = []
    for spec in PACKAGES:
        staging, written = write_package(spec)
        staged.append((staging, ROOT / spec["file"], written, spec["file"]))
        for name, count in written.items():
            if count > 150:
                too_long.append((spec["file"], name, count))
    test_jobs = [
        (ROOT / "tests/test_dialer_session.py", []),
        (ROOT / "tests/test_transcript_storage.py", ["prospect", "FakeSupabaseClient"]),
    ]
    for path, fixtures in test_jobs:
        staging, written = split_tests(path, fixtures)
        staged.append((staging, path, written, str(path.relative_to(ROOT))))
        for name, count in written.items():
            if count > 150:
                too_long.append((str(path.relative_to(ROOT)), name, count))
    for _staging, _original, written, label in staged:
        print(label)
        for name, count in written.items():
            mark = " OVER" if count > 150 else ""
            print(f"  {count:4} {name}{mark}")
    if too_long:
        for staging, _original, _written, _label in staged:
            shutil.rmtree(staging, ignore_errors=True)
        raise SystemExit("files still over 150 lines")
    for staging, original, _written, _label in staged:
        commit(staging, original)


if __name__ == "__main__":
    main()
