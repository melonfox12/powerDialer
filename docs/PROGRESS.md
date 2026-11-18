# Documentation & annotation progress

Last updated: 2026-11-18 (session start)

## Phase status

| Phase | Status | Notes |
|-------|--------|--------|
| Phase 1 — Handbook | **complete** | `docs/HANDBOOK.md` + `docs/handbook/01`–`12` |
| Phase 2 — Line annotations | **in progress** | Next batch **B02** (`web.py`) |

## Scope

Annotate **comments only** (add; never change code). Sidecars in `docs/annotated-sidecars/` for non-commentable formats if needed.

### Include

- **Python** (`*.py`): ~100 files — `server.py`, `web.py`, `features/`, `shared/`, `_web/`, `scripts/`, `tests/`
- **JavaScript** (`static/**/*.js`): ~95 module files (ES modules, no bundler)
- **HTML** (`static/**/*.html`): shell + feature partials
- **CSS** (`static/css/**/*.css`): numbered + `linear/` overrides

### Skip (document only)

| Path | Reason |
|------|--------|
| `.env`, `crm_data/**` | User rule: never touch |
| `node_modules/**`, lock/minified/generated binaries | Ground rules |
| `docs/page-before.html` | Frozen HTML snapshot for design regression (not runtime source) |
| `.cursor/**`, `AGENTS.md` | Cursor/meta, not app runtime |
| `docs/linear-design-system/**` | External design notes, not executable app code |
| Empty `__init__.py` | Header comment only unless code appears later |

### Verification (each batch)

1. `python scripts/verify_comment_only.py <files...>` — strip comments, diff against `git show HEAD:path`
2. `python -m unittest discover -s tests -q` (or project test command)
3. On failure: revert file, note in this file under **Reverted**

## Batch plan (Phase 2)

Order: core backend → dialer internals → prospects → AI voice → web glue → frontend core → feature UI → CSS/HTML → tests → scripts.

| Batch | Files | Annotated? |
|-------|-------|------------|
| **B01** | `dialer.py`, `server.py`, `shared/config.py`, `shared/infra.py`, `shared/__init__.py` | **done** (AST verify OK) |
| **B02** | `web.py` | pending |
| **B03** | `shared/vocabulary.py`, `shared/api_contract.py`, `shared/dial_policy.py`, `shared/pipeline_config.py` | pending |
| **B04** | `shared/_infra/files.py`, `shared/_infra/supabase.py`, `shared/_infra/__init__.py` | pending |
| **B05** | `_web/respond.py`, `_web/hooks.py`, `_web/__init__.py` | pending |
| **B06** | `features/accounts.py`, `features/settings.py` | pending |
| **B07** | `features/dialer.py` | pending |
| **B08** | `features/_dialer/*.py` (state, queue, calls, twilio, …) | pending |
| **B09** | `features/_dialer/_call_events/*.py` | pending |
| **B10** | `features/prospects.py`, `features/_prospects/*.py` | pending |
| **B11** | `features/metrics.py`, `features/performance.py` | pending |
| **B12** | `features/ai_*.py`, `features/ai_voice_*.py`, `features/ai_media_bridge.py` | pending |
| **B13** | `static/main.js`, `static/core.js`, `static/_core/*` | pending |
| **B14** | `static/features/*.js` + `static/features/_dialer/*` | pending |
| **B15** | `static/features/_prospects/*`, `_performance/*`, `_pipeline/*`, `_workflow/*`, `_ai_dialer/*`, `_arcade/*` | pending |
| **B16** | `static/**/*.html`, `static/css/**` | pending |
| **B17** | `tests/**` | pending |
| **B18** | `scripts/**` | pending |
| **B19** | `features/__init__.py`, remaining empty inits | pending |

## Files done (annotations)

- B01: `dialer.py`, `server.py`, `shared/config.py`, `shared/infra.py`, `shared/__init__.py`

## Reverted / failed verification

_None yet._

## Handbook files

| File | Done? |
|------|-------|
| `docs/HANDBOOK.md` | done |
| `docs/handbook/01-overview.md` | done |
| `docs/handbook/02-system-map.md` | done |
| `docs/handbook/03-folders.md` | done |
| `docs/handbook/04-tech-stack.md` | done |
| `docs/handbook/05-concepts.md` | done |
| `docs/handbook/06-data-model.md` | done |
| `docs/handbook/07-information-flow.md` | done |
| `docs/handbook/08-user-traces.md` | done |
| `docs/handbook/09-background-realtime.md` | done |
| `docs/handbook/10-configuration.md` | done |
| `docs/handbook/11-api-reference.md` | done |
| `docs/handbook/12-glossary.md` | done |
| `docs/ISSUES.md` | done (seeded) |

## Notes / decisions

- Local mode uses JSON under `crm_data/` and `metrics.json`; cloud mode uses Supabase tables in `docs/supabase/schema.sql` (server uses **service_role** key, not browser anon for writes).
- Twilio callbacks listen on **HOOK_PORT** 8765 (`_web/hooks.py`), separate from the CRM app on **APP_PORT** 8000.
- Frontend has **no SPA router**; tabs switch via `static/_core/navigation.js`.
- AI media may run embedded or as `scripts/ai_media_bridge.py` (WebSocket bridge to Cartesia/OpenAI).