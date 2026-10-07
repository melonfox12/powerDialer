#!/usr/bin/env python3
"""Import existing local JSON data into Supabase without overwriting other records."""

import argparse
import os
import uuid

from shared.config import read_env
from shared.infra import SupabaseClient

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def migrate_local_data(client, crm_path, metrics_path, user_id):
    """Import local JSON data without overwriting different remote records."""
    from features.prospects import ProspectStore
    from features.metrics import MetricsStore

    prospects = ProspectStore(crm_path).leads
    metric_data = MetricsStore(metrics_path).data
    local_prospects = {lead["id"]: lead for lead in prospects}
    local_daily = {
        (day, key): value
        for day, values in metric_data.get("daily", {}).items()
        for key, value in values.items()
    }
    local_totals = metric_data.get("all_time", {})

    existing_prospects = client.select_all("prospects", {"select": "id,data"})
    existing_daily = client.select_all(
        "dialer_metric_daily", {"select": "day,metric_key,value"}
    )
    existing_totals = client.select_all(
        "dialer_metric_totals", {"select": "metric_key,value"}
    )
    existing_sessions = client.select_all("dialer_sessions", {"select": "id,data"})
    for row in existing_prospects:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid prospect record.")
        if local_prospects.get(row.get("id")) != row.get("data"):
            raise ValueError("Migration stopped: Supabase contains prospect data that differs from local data.")
    for row in existing_daily:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid daily metric.")
        if local_daily.get((str(row.get("day")), row.get("metric_key"))) != row.get("value"):
            raise ValueError("Migration stopped: Supabase contains daily metrics that differ from local data.")
    for row in existing_totals:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid all-time metric.")
        if local_totals.get(row.get("metric_key")) != row.get("value"):
            raise ValueError("Migration stopped: Supabase contains all-time metrics that differ from local data.")
    local_sessions = {
        session["id"]: session for session in metric_data.get("sessions", [])
        if isinstance(session, dict) and session.get("id")
    }
    for row in existing_sessions:
        if not isinstance(row, dict):
            raise ValueError("Migration stopped: Supabase contains an invalid session.")
        if local_sessions.get(row.get("id")) != row.get("data"):
            raise ValueError("Migration stopped: Supabase contains session data that differs from local data.")
    for start in range(0, len(prospects), 500):
        batch = prospects[start:start + 500]
        client.request(
            "POST",
            "prospects",
            {"on_conflict": "id"},
            [{"id": lead["id"], "user_id": user_id, "data": lead} for lead in batch],
            "resolution=merge-duplicates,return=minimal",
        )
    daily_rows = [
        {"user_id": user_id, "day": day, "metric_key": key, "value": value}
        for day, values in metric_data.get("daily", {}).items()
        for key, value in values.items()
        if value
    ]
    total_rows = [
        {"user_id": user_id, "metric_key": key, "value": value}
        for key, value in metric_data.get("all_time", {}).items()
        if value
    ]
    for table, rows in (
        ("dialer_metric_daily", daily_rows),
        ("dialer_metric_totals", total_rows),
    ):
        for start in range(0, len(rows), 500):
            client.request(
                "POST", table, payload=rows[start:start + 500],
                prefer="resolution=merge-duplicates,return=minimal",
            )
    sessions = list(local_sessions.values())
    for start in range(0, len(sessions), 500):
        client.request(
            "POST",
            "dialer_sessions",
            payload=[{
                "id": session["id"],
                "user_id": user_id,
                "started_at": session["started_at"],
                "ended_at": session.get("ended_at"),
                "data": session,
            } for session in sessions[start:start + 500]],
            prefer="resolution=merge-duplicates,return=minimal",
        )
    return {"prospects": len(prospects), "daily_metrics": len(daily_rows), "totals": len(total_rows)}

def _user_id(value):
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--user-id must be the Supabase auth user UUID.") from exc


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--user-id", required=True, type=_user_id,
        help="Supabase auth user id (Authentication > Users) that will own the imported rows.",
    )
    args = parser.parse_args(argv)
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
        args.user_id,
    )
    print(
        "Imported "
        f"{result['prospects']} prospects, {result['daily_metrics']} daily metric values, "
        f"and {result['totals']} all-time metric values."
    )


if __name__ == "__main__":
    main()
