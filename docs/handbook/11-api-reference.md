# 11. API and endpoint reference

Routing: `web.all_routes()` = `SYSTEM_ROUTES` + feature `ROUTES` tuples `(METHOD, path, handler, profile)`.

**Profiles:** `none` (no account), `GET reads` (storage errors → 502), `voice-token`, `bridge` (AI), `POST`, `debug`.

For JSON shapes see `docs/ARCHITECTURE.md` and `shared/api_contract.py`. Below: **purpose, caller, side effects**.

## System (`web.py`)

| Method | Path | Handler | Auth | Side effects |
|--------|------|---------|------|--------------|
| GET | `/api/auth/config` | `get_auth_config` | Public | None |
| GET | `/api/health` | `get_health` | Public | Supabase ping cache 30s |
| GET | `/api/auth/me` | `get_auth_me` | Account | None |
| POST | `/api/debug` | `ingest_client_debug` | Public (Host) | Appends debug log |

## Settings (`features/settings.py`)

| Method | Path | Handler | Side effects |
|--------|------|---------|--------------|
| GET | `/api/settings` | `get_settings` | Read settings view |
| POST | `/api/settings` | `post_settings` | Writes `.env` and/or `dialer_settings`; reload Twilio |

## Metrics & performance (`features/metrics.py`)

| Method | Path | Handler | Side effects |
|--------|------|---------|--------------|
| GET | `/api/metrics` | `get_metrics` | Read bump counters |
| GET | `/api/performance` | `get_performance` | Aggregate CRM call logs |
| POST | `/api/performance/goal` | `post_goal` | Update goal prefs |
| POST | `/api/bookings` | `post_booking` | Set `booked_at` on lead, metrics |

## Prospects (`features/prospects.py`)

| Method | Path | Handler | Side effects |
|--------|------|---------|--------------|
| POST | `/api/leads` | `post_lead` | Create lead |
| POST | `/api/leads/{id}/fields` | `post_fields` | Patch `fields` |
| POST | `/api/leads/{id}/pipeline` | `post_pipeline_step` | Pipeline move |
| POST | `/api/pipeline/settings` | `post_save_pipeline_settings` | Custom steps JSON |
| POST | `/api/import` | `post_import` | CSV bulk create |
| GET | `/api/export.csv` | `get_export` | Download CRM CSV |
| DELETE | `/api/leads/{id}` | `delete_lead` | Remove lead |

## Dialer (`features/dialer.py`) — selected

| Method | Path | Handler | Side effects |
|--------|------|---------|--------------|
| GET | `/api/state` | `get_state` | Full dialer snapshot |
| GET | `/api/live` | `get_live` | Poll snapshot (no pool) |
| GET | `/api/leads` | `get_leads` | CRM + pool catalog |
| GET | `/api/leads/summary` | `get_leads_summary` | Slim lead list |
| GET | `/api/voice-token` | `get_voice_token` | Twilio capability JWT |
| POST | `/api/voice/rejoin` | `post_voice_rejoin` | Reattach browser leg |
| POST | `/api/timezone` | `post_timezone` | Filter pool timezone |
| POST | `/api/caller-id-group` | `post_caller_id_group` | Outbound caller ID set |
| POST | `/api/start` | `post_start` | Start dialing session |
| POST | `/api/pause` | `post_pause` | Pause |
| POST | `/api/stop` | `post_stop` | End session |
| POST | `/api/hangup` | `post_hangup` | Hang active calls |
| POST | `/api/skip` | `post_skip` | Skip current lead |
| POST | `/api/next/skip` | `post_pass_next` | Pass / queue skip |
| POST | `/api/advance` | `post_advance` | Wrap-up advance |
| POST | `/api/dials/scan` | `post_scan_crm` | CRM maintenance |
| POST | `/api/leads/{id}/dial` | `post_dial` | Manual single-lead dial |
| POST | `/api/leads/{id}/status` | `post_status` | CRM status change |
| POST | `/api/leads/{id}/call-outcome` | `post_call_outcome` | Disposition + call log |
| GET/POST | `/api/dials/*` | various | Import/export/archive records |
| GET/POST | `/api/ai-agents/*` | various | AI fleet, playbook, sandbox |

Full list: `ROUTES` in `features/dialer.py` lines ~553–594.

## AI voice bridge (`features/ai_voice_routes.py`)

| Method | Path | Handler | Auth |
|--------|------|---------|------|
| GET | `/api/ai-voice/bootstrap` | `get_ai_voice_bootstrap` | Bridge secret |
| GET | `/api/ai-voice/stream-sync` | `get_ai_voice_stream_sync` | Bridge |
| POST | `/api/ai-voice/stream-started` | `post_ai_voice_stream_started` | Bridge |
| POST | `/api/ai-voice/stream-stopped` | `post_ai_voice_stream_stopped` | Bridge |
| POST | `/api/ai-voice/inbound` | `post_ai_voice_inbound` | Bridge |

## Twilio hooks (`_web/hooks.py`) — not in `ROUTES`

| Path | Methods | Handler on `Dialer` |
|------|---------|---------------------|
| `/hooks/voice` | GET/POST | `handle_client_voice` |
| `/hooks/{token}/{action}` | GET/POST | `handle_webhook` |

## Key backend classes (non-HTTP)

| Symbol | File | Called by |
|--------|------|-----------|
| `AppRuntime.configure` | `features/accounts.py` | `server.serve` |
| `resolve_account` | `features/accounts.py` | `AppHandler.open_account` |
| `Dialer` | `features/dialer.py` | Routes, webhooks, AI |
| `ProspectStore` | `features/prospects.py` | Dialer, prospect routes |
| `maintain_crm` | `features/_dialer/queue.py` | Scan endpoint, imports |
| `handle_webhook` | `features/_dialer/call_events.py` | Hooks server |
| `SupabaseClient` | `shared/_infra/supabase.py` | Stores, auth |