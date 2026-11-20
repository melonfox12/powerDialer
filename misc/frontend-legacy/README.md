# Legacy frontend (dialer era)

Human dialer, AI dialer agent, performance metrics, caller pool, total dials, arcade UI, and related CSS/JS live here. The running app under `frontend/` no longer loads these modules.

## Layout

| Path | Contents |
| --- | --- |
| `html/` | Page partials: `dialer.html`, `ai-dialer-agent.html`, `performance.html`, `session-summary-dialog.html` |
| `js/features/` | Entry scripts: `dialer.js`, `ai-dialer-agent.js`, `performance.js`, `arcade.js` |
| `js/_dialer/` | Human dialer controllers, voice, pool, dials |
| `js/_ai_dialer/` | AI fleet and sandbox UI |
| `js/_performance/` | Metrics charts |
| `js/_arcade/` | Sensory feedback |
| `css/` | Monitor, charts, arcade, and linear overrides for dialer tabs |

Imports in these files still reference `../../_core` and `../core.js` as if they lived under `frontend/features/`. To revive a legacy tab, move the relevant files back under `frontend/`, restore HTML partials in `_web/respond.py` `send_app_page`, and re-wire `frontend/main.js`.

Dial-only settings markup (audio test, call flow, arcade) belongs with this tree; the live `frontend/features/settings.html` keeps integrations only and preserves dialer preference fields on save via `state.settings`.