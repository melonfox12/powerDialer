# 8. End-to-end user traces

Each trace lists **files and functions in order**. Data shapes refer to `shared/api_contract.py`.

---

## A. Sign-in (Supabase + Google)

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `static/main.js` | `initAuth()` from `static/features/auth.js` |
| 2 | `GET /api/auth/config` | `web.get_auth_config` → `{ google, url, anonKey }` |
| 3 | `auth.js` | If `google`, create Supabase client, OAuth redirect |
| 4 | Browser | Google OAuth → Supabase session access token |
| 5 | `static/_core/api.js` | Attaches `Authorization: Bearer` on API fetches |
| 6 | `web.AppHandler.open_account` | `features/accounts.resolve_account` → JWT via `SupabaseClient.auth_user` |
| 7 | `AppRuntime.session_for` | Builds per-user `Account` + `Dialer` with `load_app_settings` |
| 8 | `GET /api/auth/me` | `get_auth_me` → `{ id, email }` for UI chrome |

**Local mode (no Supabase):** steps 2–7 collapse; `resolve_account` may bind `runtime.local` without bearer.

---

## B. View and filter CRM leads

| Step | Location | What happens |
|------|----------|--------------|
| 1 | Tab → Prospects | `navigation.setDashboardTab` shows `#prospectsTabPanel` |
| 2 | `poller.refreshState` | `GET /api/leads` when version changes |
| 3 | `features/dialer.get_leads` | `projection.leads_catalog(dialer)` |
| 4 | `sync-state.js` | Merges `leads`, `pool`, `counts` into `state` |
| 5 | `prospects.js` / `table.js` | `renderTable()` reads filters from DOM (`searchInput`, `statusFilter`, …) |
| 6 | `query.js` | Client-side filter only; no server query params on `/api/leads` |

**Data:** Input filters are strings/numbers in DOM; output is filtered view of `state.leads`.

---

## C. Move lead through pipeline

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `pipeline.js` / `board.js` | User drags card or picks step |
| 2 | UI | `POST /api/leads/{id}/pipeline` body `{ pipeline_step }` |
| 3 | `prospects.post_pipeline_step` | Validates step, updates lead, history |
| 4 | `ProspectStore.save` | Backend write (local or Supabase) |
| 5 | Response | Often includes updated `lead` + dialer `state` |
| 6 | `sync-state` + `render` | Pipeline board + CRM table refresh |

Pipeline step definitions from `pipeline_steps` in leads payload (vocabulary + custom JSON settings).

---

## D. Manual power-dial session + save call log

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `dialer.js` `bindDialer` | Wire start/pause/hangup buttons |
| 2 | `POST /api/start` | `dialer.post_start` → queue arms, session stats |
| 3 | `Dialer` + `_dialer/calls.py` | Twilio REST outbound; slots in `in_flight` |
| 4 | Browser | If `requires_browser_voice`, `GET /api/voice-token` + Twilio Device connect |
| 5 | Twilio → `hooks.py` | Status callbacks → `handle_webhook` / `handle_client_voice` |
| 6 | `_call_events/pickup.py`, `ended.py` | Stage transitions, talk time, AMD |
| 7 | `poller` | `GET /api/live` shows `stage`, `live_transcript`, `in_flight` |
| 8 | User sets outcome | `POST /api/leads/{id}/call-outcome` or status buttons |
| 9 | `outcomes.py` | Maps disposition → status, appends `call_log` entry |
| 10 | CRM save + metrics bump | Persistent log; `MetricsStore.bump` for counters |

**Data passed:** `lead_id`, `outcome` key, optional notes; server returns `{ state, lead }`.

---

## E. View analytics (Performance tab)

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `performance.js` | Tab activation runs `renderMetrics` |
| 2 | `GET /api/performance?range=week&tz=...` | `metrics.get_performance` |
| 3 | `features/performance.py` | Aggregates CRM `call_log`, bookings |
| 4 | `_performance/charts.js` | Builds line/pie charts in canvas/SVG per HTML |
| 5 | Optional | `GET /api/metrics` for bump counters (15s poll) |

---

## F. AI dialer agent (summary)

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `ai-dialer-agent.js` | Fleet UI, start/stop agent seats |
| 2 | `POST /api/ai-agents/start` etc. | `features/dialer.py` handlers delegate to `ai_agents.py` |
| 3 | Media bridge | Audio via `ai_media_bridge` + `/api/ai-voice/*` |
| 4 | LLM/STT/TTS | `ai_voice_llm.py`, `ai_voice_stt.py`, `ai_voice_cartesia.py` |

See `docs/AI_VOICE.md` for stream-level detail.

---

## G. Settings / Twilio credentials

| Step | Location | What happens |
|------|----------|--------------|
| 1 | `settings.js` | Form bind |
| 2 | `POST /api/settings` | `settings.post_settings` → merge secrets, `write_env` or Supabase row |
| 3 | `FeatureContext.reload_settings` | Twilio client refreshed on dialer |
| 4 | `GET /api/settings` | Redacted view with `has_*` flags |