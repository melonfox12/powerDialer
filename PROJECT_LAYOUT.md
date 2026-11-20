# Project layout (in use vs misc)

## Main tree — runtime

| Area | Path | Role |
| --- | --- | --- |
| Entry | `server.py`, `web.py`, `dialer.py` | HTTP servers and Twilio hooks |
| Backend | `features/`, `shared/`, `_web/` | `/api/*` (unchanged; dialer + AI routes still exist for Twilio/workflows) |
| Frontend | `frontend/` | Active SPA: CRM, Workflow, Pipeline only |
| Checks | `scripts/check_static.py` | Validates `frontend/` imports and DOM ids |

## Active frontend surface

| Tab | Modules | Primary APIs |
| --- | --- | --- |
| Global CRM | `features/prospects.*`, `_prospects/*` | `/api/leads`, import/export, `/api/live` |
| Workflow | `features/workflow.*`, `_workflow/*` | `/api/campaigns`, flow, import, stats |
| Pipeline | `features/pipeline.*`, `_pipeline/*` | `/api/leads/{id}/pipeline`, `/api/pipeline/settings` |
| Shell | `auth.js`, `settings.js`, `_core/poller.js` | `/api/auth/*`, `/api/settings`, `/api/live`, `/api/metrics` |

Boot: `frontend/main.js` → `features/pipeline.js`, `workflow.js`, `prospects.js`, `settings.js`, `auth.js`.

## `misc/` — not loaded by the app

| Subfolder | Contents |
| --- | --- |
| `misc/frontend-legacy/` | Dialer, AI agent, performance, pool, dials, arcade (HTML, JS, CSS) |
| `misc/frontend-unused/` | Dead workflow experiments |
| `misc/docs/` | Design notes and `page-before.html` snapshot |
| `misc/scripts/` | Regenerate snapshot, one-off generators |

Regenerate the HTML snapshot after page changes:

`python misc/scripts/regen_page_before.py`