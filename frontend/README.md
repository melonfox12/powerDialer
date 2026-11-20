# Frontend (browser app)

**Active product:** Global CRM, Workflow, and Pipeline (`frontend/_core/navigation.js`).

Boot: `main.js` loads `auth.js`, `prospects.js`, `workflow.js`, `pipeline.js`, `settings.js`, and `_core/poller.js` for `/api/live`.

Page partials (see `_web/respond.py`): `shell.html` → `features/app-frame.html` → workflow / pipeline / prospects panels → `settings.html` → `shell-end.html`.

Legacy dialer UI lives in `misc/frontend-legacy/`, not served by default.

See `PROJECT_LAYOUT.md` at the repo root.