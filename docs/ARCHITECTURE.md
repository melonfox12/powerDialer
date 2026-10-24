# HTTP API contract

Runtime behavior is unchanged by this document. **Source of truth for top-level JSON keys** is `shared/api_contract.py`. Integration tests in `tests/test_http.py` and `tests/test_api_contract.py` assert responses match those tuples.

## Dialer read endpoints

### `GET /api/state`

Full dialer snapshot for boot or debugging. Same shape as the `state` object returned on many POST mutations. Does **not** include the full `leads` array (use `GET /api/leads`).

Top-level keys: `DIALER_STATE_KEYS` in `shared/api_contract.py`.

Notable nested objects:

| Field | Keys / notes |
|-------|----------------|
| `settings` | `DIALER_SETTINGS_KEYS` (subset of session preferences exposed to the UI) |
| `session_stats` | `SESSION_STATS_KEYS` (defaults from `new_session()` when idle; `connect_times` is server-only and stripped) |
| `counts` | `COUNTS_KEYS` |
| `in_flight[]` | `IN_FLIGHT_KEYS` per row (`lead` is embedded lead or null) |
| `live_transcript` | `LIVE_TRANSCRIPT_KEYS` |
| `activity_log[]` | `ACTIVITY_LOG_ENTRY_KEYS` per entry |
| `pool` | Array of `LeadRecord` rows eligible to dial |
| `active_lead`, `next_lead`, `pending_outcome` | `LeadRecord` or null |
| `stage` | One of `idle`, `dialing`, `ringing`, `connected`, `wrapup`, `paused` (`shared/vocabulary.STAGES`) |

### `GET /api/live`

Lightweight poll payload used every ~1.5s while the app is open. Same as `GET /api/state` **except** `pool` is omitted.

Top-level keys: `LIVE_STATE_KEYS`.

### `GET /api/leads`

CRM catalog for the prospects table and caller pool.

Top-level keys: `LEADS_CATALOG_KEYS` — `leads`, `pool`, `leads_version`, `timezone_groups`, `counts`.

## Lead record

Prospects are JSON objects stored in CRM and echoed in API responses.

Required keys on every lead (`LEAD_KEYS`): `id`, `name`, `business`, `phone`, `timezone`, `status`, `scheduled_until`, `transcript`, `fields`.

Common optional keys (`LEAD_OPTIONAL_KEYS`): `call_log`, `booked_at`, `passed_at`, `status_history`.

Call log rows use `CALL_LOG_ENTRY_KEYS`. Typed shape: `LeadRecord` in `shared/api_contract.py`.

Status values: `shared/vocabulary.CRM_STATUS_KEYS`.

## Metrics endpoints

### `GET /api/metrics`

Legacy **bump counter** store (dials / connected / booked per day). Written during dialing via `MetricsStore.bump`, not derived from CRM call logs.

Top-level keys: `METRICS_SNAPSHOT_KEYS` — `today`, `all_time`, `daily`.

Each `daily[]` row: `METRICS_DAILY_ROW_KEYS`.

### `GET /api/performance?range=&tz=`

**CRM-derived** analytics for the Performance tab (funnel, trend, today’s goals).

Query:

- `range` — `day`, `week`, or `month` (legacy aliases `today`, `7d`, `all` are mapped in `features/metrics.py`).
- `tz` — IANA timezone name for day boundaries.

Top-level keys: `PERFORMANCE_PAYLOAD_KEYS`.

Nested:

| Field | Keys |
|-------|------|
| `counts` | `PERFORMANCE_COUNTS_KEYS` |
| `funnel` | `PERFORMANCE_FUNNEL_KEYS` |
| `daily` | `PERFORMANCE_DAILY_KEYS` |
| `trend` | `PERFORMANCE_TREND_KEYS`; each bucket uses `PERFORMANCE_TREND_BUCKET_KEYS` |

`conversation_min_seconds` matches `shared/vocabulary.CONVERSATION_MIN_SECONDS` for CRM “conversation” definition on this page.

### Relationship between `/api/metrics` and `/api/performance`

| | `/api/metrics` | `/api/performance` |
|--|----------------|-------------------|
| Data source | Metrics store bumps | CRM `call_log` + booking timestamps |
| Primary UI | Legacy / session bumps | Performance tab |
| “Conversation” | Not defined here | `performance.is_conversation()` |

New work should prefer **performance** for user-facing analytics unless you intentionally need bump counters.

## Settings

`GET /api/settings` returns `SETTINGS_VIEW_KEYS` (Twilio + goals + storage metadata). Secrets are redacted; `has_auth_token` / `has_api_secret` indicate stored values.

## Mutations returning `state`

Many `POST` routes return `{"state": …}` or embed the dialer snapshot with the same keys as `DIALER_STATE_KEYS`. Examples: `/api/start`, `/api/timezone`, `/api/leads/{id}/status`.

CRM maintenance (`remember_open_skips`, dial-cap backfill) runs on explicit actions (scan, import, call-log writes), not on these GET endpoints. See `queue.maintain_crm()` in `features/_dialer/queue.py`.
