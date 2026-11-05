"""One-time CRM migration flags stored beside local CRM data."""

import json
from pathlib import Path


def _flags_path(crm_path):
    path = Path(crm_path)
    base = path if path.is_dir() or not path.suffix else path.parent
    return base / ".crm_migrations.json"


def migration_done(crm_path, key):
    flags_path = _flags_path(crm_path)
    try:
        data = json.loads(flags_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get(key))


def mark_migration_done(crm_path, key):
    flags_path = _flags_path(crm_path)
    data = {}
    try:
        if flags_path.is_file():
            data = json.loads(flags_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
    except (OSError, json.JSONDecodeError):
        data = {}
    data[key] = True
    flags_path.parent.mkdir(parents=True, exist_ok=True)
    flags_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
