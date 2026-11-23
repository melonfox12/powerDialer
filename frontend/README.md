# Frontend (browser app)

**Active tabs (top chrome):** Dialer (manual power dialer) · Call log · Global CRM.

Dialer stack restored from git `a0d4552` (pre-legacy archive): `features/dialer.html`, `features/dialer.js`, `features/_dialer/*`, arcade, full settings, prospects + dials panels.

`ai-dialer-agent.html` is still concatenated into the page so untouched dialer modules keep their DOM ids; the AI tab is not wired in `main.js`.

Workflow / pipeline UI lives in `misc/frontend-workflow-pipeline/`.

Boot: `main.js` — dialer, prospects, settings, auth, arcade, poller via `features/dialer.js`.