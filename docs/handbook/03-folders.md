# 3. Folder and file map

## Repository root

| Path | Responsibility |
|------|----------------|
| `dialer.py` | CLI entry; calls `server.serve()` |
| `server.py` | Starts app + hook HTTP servers, `AppRuntime.configure()` |
| `web.py` | Route table, `AppHandler`, auth gate, dispatches to feature handlers |
| `requirements.txt` | Python deps: `twilio`, `tzdata`, `websockets` |
| `AGENTS.md` | Contributor architecture rules |

## `_web/` — HTTP presentation glue

| File | Role |
|------|------|
| `respond.py` | Assembles `GET /` from `static/` partials; serves static files; JSON helpers; debug log |
| `hooks.py` | Twilio-only server: validates signature, forwards to `Dialer.handle_webhook` |

## `shared/` — cross-cutting constants and infra

| File | Role |
|------|------|
| `vocabulary.py` | **Single source** for statuses, metrics keys, timezones, setting keys, browser vocab export |
| `dial_policy.py` | Pure rules: pool eligibility, dial caps, callbacks, connect detection helpers |
| `api_contract.py` | TypedDict + key tuples for JSON API shape (tests enforce) |
| `pipeline_config.py` | Default pipeline steps and locked columns |
| `config.py` | Paths, ports, `read_env` / `write_env`, public API allowlist |
| `infra.py` | Re-exports Supabase client, debug log, atomic JSON, UTC clock |
| `_infra/supabase.py` | Minimal REST client (no official SDK) |
| `_infra/files.py` | `debug_event`, `write_json_atomic`, logging enable |

## `features/` — HTTP routes and business workflows

| File / folder | Role |
|---------------|------|
| `accounts.py` | `AppRuntime`, per-user `Account`, Supabase vs local storage choice, JWT resolution |
| `settings.py` | `GET/POST /api/settings`, `.env` + `dialer_settings` row |
| `prospects.py` | CRM CRUD routes, `ProspectStore` facade |
| `_prospects/` | Local vs Supabase backends, CSV, dial archive/records |
| `dialer.py` | `Dialer` session class, dialer API routes, Twilio facade methods |
| `_dialer/` | Queue, calls, slots, outcomes, projection, Twilio, voice session, AI hooks |
| `metrics.py` | Bump metrics + `GET /api/performance` |
| `performance.py` | CRM analytics aggregation |
| `ai_agents.py`, `ai_agent_*`, `ai_voice_*` | AI fleet, sandbox, Cartesia/STT/LLM, media bridge routes |

## `static/` — frontend (no build step)

| Path | Role |
|------|------|
| `shell.html` / `shell-end.html` | App chrome, CSS links, `#loginGate` |
| `main.js` | Boot: bind all features, `startPolling()` |
| `core.js` | Re-exports for convenience |
| `_core/` | `state.js`, `api.js`, `navigation.js`, `render.js`, `registry.js`, format helpers |
| `features/` | One HTML partial + entry `*.js` per tab; subfolders `_dialer`, `_prospects`, etc. |
| `css/` | `01-tokens.css` … `09-shell.css`, then `css/linear/*` overrides |

## `tests/` — `unittest` integration suite

Exercises HTTP routes, dialer session, dial policy, prospects, Supabase mocks, static asset checks.

## `scripts/` — maintenance

| Script | Role |
|--------|------|
| `migrate_to_supabase.py` | One-way local JSON → Supabase import |
| `ai_media_bridge.py` | Standalone WebSocket bridge process |
| `check_static.py` | Static reference checks |
| `verify_comment_only.py` | Annotation batch verification |