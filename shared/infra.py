# -----------------------------------------------------------------------------
# File: shared/infra.py
# Purpose: Thin re-export facade so feature code imports one module for I/O helpers.
# Exports: SupabaseClient, _ConnectionPool, debug_event, enable, utc_now, write_json_atomic.
# Imported by: features/*, shared/config consumers, tests.
# Depends on: shared/_infra/files.py, shared/_infra/supabase.py
# -----------------------------------------------------------------------------
"""Process infrastructure: Supabase client, debug log, clock, atomic JSON."""

# Re-export Supabase HTTP client and its connection pool from the lower layer.
from shared._infra.files import debug_event, enable, utc_now, write_json_atomic
from shared._infra.supabase import SupabaseClient, _ConnectionPool

# Explicit public surface for `from shared.infra import ...`.
__all__ = [
    "SupabaseClient",
    "_ConnectionPool",
    "debug_event",
    "enable",
    "utc_now",
    "write_json_atomic",
]