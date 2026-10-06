#!/usr/bin/env python3
"""Import existing local JSON data into Supabase without overwriting other records."""

import os

from shared.config import read_env
from supabase_store import SupabaseClient, migrate_local_data

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    values = read_env(os.path.join(APP_DIR, ".env"))
    client = SupabaseClient.from_env(values)
    if not client:
        raise SystemExit(
            "Set SUPABASE_URL and SUPABASE_SECRET_KEY (or SUPABASE_SERVICE_ROLE_KEY) "
            "in .env or the process environment first."
        )
    result = migrate_local_data(
        client,
        os.path.join(APP_DIR, "crm_data"),
        os.path.join(APP_DIR, "metrics.json"),
    )
    print(
        "Imported "
        f"{result['prospects']} prospects, {result['daily_metrics']} daily metric values, "
        f"and {result['totals']} all-time metric values."
    )


if __name__ == "__main__":
    main()
