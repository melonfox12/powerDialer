# Misc (out of runtime path)

Nothing here is served or imported when you run `server.py` / `dialer.py`.

- **`docs/`** — planning snapshots and Supabase notes; `page-before.html` is compared in `tests/test_http.py`.
- **`scripts/`** — one-off maintainers (regen HTML snapshot, AI dialer partial, list orphan frontend files).
- **`frontend-unused/`** — frontend modules that are not reachable from `frontend/main.js` (moved out of `frontend/`).
- **`frontend-legacy/`** — full dialer / AI agent / performance stack (HTML, JS, CSS); see its README to restore.

Active app code lives in the repo root: `frontend/` (CRM + workflow + pipeline only), `features/`, `shared/`, `_web/`.