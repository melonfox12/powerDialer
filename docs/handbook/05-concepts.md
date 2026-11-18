# 5. Core concepts

## Single-page assembly (no router)

The server builds one HTML page by concatenating partials (`_web/respond.py` → `send_app_page`). Tabs only toggle CSS/display via `setDashboardTab` in `static/_core/navigation.js`. Deep linking to tabs is limited; state lives in JS `state` object and server snapshots.

## Account and runtime

`AppRuntime` (`features/accounts.py`) chooses storage at startup:

- **No Supabase URL/key** → one shared `Account` with local JSON (`runtime.local`).
- **Supabase configured** → per signed-in user `Account` in `runtime.sessions[user_id]`.

Each `Account` holds: `crm` (`ProspectStore`), `metrics`, `dialer` (`Dialer`), `dial_archive`, `dial_records`.

## Dialer session

`Dialer` is the in-memory **orchestrator** for one user's calling session:

- **Queue / pool** — which leads are callable (`shared/dial_policy.py` rules).
- **Stages** — `idle`, `dialing`, `ringing`, `connected`, `wrapup`, `paused` (`shared/vocabulary.STAGES`).
- **In-flight slots** — parallel dial lines until first human pickup.
- **Twilio integration** — initiate, hang up, parse webhooks (`features/_dialer/call_events.py`).
- **Projection** — builds JSON for `GET /api/state`, `/api/live`, `/api/leads` (`features/_dialer/projection.py`).

## Lead record

A prospect is a **JSON object** (not normalized SQL columns except in Supabase wrapper). Required keys: see `LEAD_KEYS` in `shared/api_contract.py`. Status is a string key from `shared/vocabulary.STATUS_KEYS`. Extra CSV columns land in `fields`.

## Dial policy (pure rules)

`shared/dial_policy.py` centralizes:

- Which statuses enter the auto-dial pool (`DIAL_POOL_STATUSES`).
- Never-dial statuses (`booked`, `proposal_sent`, `closed`).
- Callback timers (`scheduled_until` on `dialed` status).
- Connect vs not-connected call answers (`NOT_CONNECTED_CALL_ANSWERS`).
- Five-strike no-contact cap → `closed`.

Changing business rules should happen **here**, not duplicated in UI or storage layers.

## Metrics: two systems

1. **Bump store** — `MetricsStore.bump` on discrete events; exposed as `GET /api/metrics`.
2. **Performance analytics** — scans CRM `call_log` in `features/performance.py`; `GET /api/performance`.

See `docs/ARCHITECTURE.md` for when to use which.

## Browser state and polling

`static/_core/state.js` holds client copy of `leads`, `pool`, `metrics`, dialer flags. `static/features/_dialer/poller.js` `refreshState`:

- Every ~1.5s: `GET /api/live`
- When `leads_version` changes: `GET /api/leads`
- Every 15s: `GET /api/metrics`

`render()` → `runRenderers()` only paints the active tab's registered renderers (`registry.js`).

## Auth model

| Endpoint | Auth |
|----------|------|
| `GET /api/auth/config` | None — tells UI if Google/Supabase is available |
| `GET /api/health` | None |
| `POST /api/debug` | None (localhost Host check only) |
| Most `/api/*` | `Authorization: Bearer <Supabase access token>` when Supabase mode; local mode may allow unauthenticated access to local account |
| Twilio webhooks | Twilio signature, not user JWT |
| AI voice bridge routes | Shared secret / public path list in `shared/config.PUBLIC_API_PATHS` |

`resolve_account` in `features/accounts.py` validates the JWT via `SupabaseClient.auth_user`.

## Webhooks vs polling

Twilio pushes call lifecycle events to the **hook server**; the UI does not use WebSockets for CRM (except AI audio bridge). Human dialer freshness depends on polling `GET /api/live`.

## Vocabulary injection

On page load, embedded JSON from `vocabulary_json()` (`shared/vocabulary.py`) gives the browser canonical labels, status keys, and metric names—**one definition** imported by both Python and the packed script in HTML.