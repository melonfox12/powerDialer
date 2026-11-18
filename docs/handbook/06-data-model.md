# 6. Data model

## Supabase tables (cloud mode)

Source: `docs/supabase/schema.sql`. The Python server writes with the **service role**; RLS policies exist for authenticated clients but the app server bypasses via service key.

### `prospects`

| Column | Type | Meaning |
|--------|------|---------|
| `id` | `text` PK | Same as `data.id` inside JSON |
| `user_id` | `uuid` | Owner (Supabase auth user) |
| `data` | `jsonb` | Full lead record (see below) |

**CRUD:** `features/_prospects/backend_supabase.py` — `POST/PATCH/DELETE` via REST; reads cached in memory with `revision` counter exposed as `leads_version`.

### `dial_archive`

Archived dial snapshots (historical dial attempts metadata). Managed by `features/_prospects/dial_archive.py`.

### `dialer_metric_daily` / `dialer_metric_totals`

| Column | Meaning |
|--------|---------|
| `user_id` | Owner |
| `day` | (daily only) UTC date bucket |
| `metric_key` | One of `METRIC_KEYS` in vocabulary |
| `value` | Non-negative integer counter |

**Writes:** `SupabaseMetricsStore.bump` calls RPC `increment_metric`.

### `dialer_sessions`

Session goal tracking rows: `id`, `user_id`, `started_at`, `ended_at`, `data` (session stats blob).

### `dialer_settings`

| Column | Meaning |
|--------|---------|
| `id` | For per-user rows: Supabase user id string; global row id `app` for local `.env` merge (`SETTINGS_ROW_ID`) |
| `data` | `jsonb` of Twilio + app settings (see `SETTING_KEYS`) |

**Reads/writes:** `features/settings.py` `load_app_settings` / `save_app_settings`.

## Lead JSON (`prospects.data`)

Documented in `docs/ARCHITECTURE.md` and `LEAD_KEYS` / `LEAD_OPTIONAL_KEYS` in `shared/api_contract.py`.

| Field | Meaning |
|-------|---------|
| `id` | Stable string id (often phone-based or UUID) |
| `name`, `business`, `phone` | Core display / dial fields |
| `timezone` | US marketing timezone label (see `TIMEZONE_NAMES` in vocabulary) |
| `status` | CRM status key (`new`, `dialed`, `contact_engaged`, …) |
| `scheduled_until` | ISO datetime when callback becomes due (on `dialed`) |
| `transcript` | Stored conversation text for CRM |
| `fields` | Arbitrary key/value from CSV or forms (reviews, city, pipeline custom fields) |
| `call_log` | Array of `CALL_LOG_ENTRY_KEYS` objects |
| `pipeline_step` | Current pipeline column key |
| `pipeline_history`, `status_history` | Auditing arrays |
| `booked_at`, `passed_at` | Timestamps for analytics |

**Created:** `POST /api/leads`, CSV `POST /api/import` → `ProspectStore.add_lead` / `add_csv`.  
**Read:** `GET /api/leads`, dialer snapshots.  
**Updated:** status/fields/pipeline POSTs, dialer outcomes, migrations in `queue.maintain_crm`.  
**Deleted:** `DELETE /api/leads/{id}`.

## Local JSON files (offline mode)

| Path | Content |
|------|---------|
| `crm_data/` | Prospect list (`part-NN.json` shards or single file) — `LocalBackend` |
| `metrics.json` | `daily`, `all_time`, `sessions` — `MetricsStore` |
| Side paths under `crm_data/` | Dial records and archives (see `dial_records.py`, `dial_archive.py`) |

## In-memory / ephemeral (not persisted as tables)

| Data | Where |
|------|--------|
| Active call slots, Twilio Call SIDs | `features/_dialer/state.py` on `Dialer` |
| Token index for webhooks | `TokenIndex` in `features/dialer.py` |
| AI voice session map | Dialer state keys `ai_voice_sessions` |
| Activity log tail | Dialer state `activity_log` (bounded list) |

## Environment / settings merge

Runtime prefs combine:

1. `.env` on disk (`shared/config.read_env`)
2. Per-account values on `Dialer.account_values` (from Supabase `dialer_settings` or `.env` after save)

Twilio credentials must be present to place real calls; redacted view exposed on `GET /api/settings`.