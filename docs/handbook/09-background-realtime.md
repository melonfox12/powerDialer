# 9. Background and realtime behavior

## Polling (primary UI sync)

| Trigger | Interval | Handler | Effect |
|---------|----------|---------|--------|
| `startPolling()` in `main.js` | ~1500 ms | `static/features/_dialer/poller.js` `refreshState` | `GET /api/live`; merges dialer snapshot |
| `leads_version` change | on demand inside poller | `GET /api/leads` | Full CRM catalog refresh |
| Metrics | ~15000 ms | `GET /api/metrics` | Updates `state.metrics` |
| Status clock | 1 s | `format.startStatusClock` | UI clock only, no server |

No WebSocket for human CRM/dialer state.

## Twilio webhooks (server-push)

| Trigger | Path pattern | Handler | State changes |
|---------|--------------|---------|---------------|
| Call status / AMD / recording | `POST /hooks/{deskToken}/{action}` | `_web/hooks.py` → `Dialer.handle_webhook` | Slots, `stage`, `in_flight`, errors |
| Client voice TwiML | `GET/POST /hooks/voice` | `handle_client_voice` | Browser leg connection |
| Signature invalid | same | 403 response | Activity log error |

Callbacks run on **port 8765**; must match `PUBLIC_BASE_URL` Twilio config.

## CRM maintenance (explicit, not cron)

| Trigger | Function | Purpose |
|---------|----------|---------|
| `POST /api/dials/scan` | `queue.maintain_crm` | Backfill callbacks, dial-cap repairs |
| CSV import, some writes | internal | May bump versions / migrations |
| Lead load | `backend_*._expire` | Clear overdue `scheduled_until` on read |

Documented in `features/_dialer/queue.py` — **never** on hot `GET /api/live` path.

## AI media bridge

| Mode | Trigger | Behavior |
|------|---------|----------|
| Embedded | `server.serve` → `maybe_start_embedded()` | Thread inside app process |
| Sidecar | `scripts/ai_media_bridge.py` | WebSocket server; HTTP back to app with `AI_BRIDGE_SECRET` |

Events: `POST /api/ai-voice/stream-started`, `stream-stopped`, `inbound`; `GET stream-sync` for bootstrap.

Uses `websockets` library; ties into `Dialer` AI session fields.

## Session lifecycle timers

Inside `Dialer` / `_dialer/timing.py`:

- Auto-advance after wrap-up (`auto_advance_delay` setting)
- Break nudges, session goal tracking
- Callback due times on leads (`scheduled_until`)

These use Python `threading.Timer` or loop checks tied to poll-driven state updates (see dialer timing module for exact mechanism).

## Debug log

`shared.infra.debug_event` appends structured lines to `debug-session.log` (enabled via `enable()` in `server.serve`). Client can `POST /api/debug` with short JSON.

## Supabase realtime

**UNSURE:** The app does not subscribe to Supabase Realtime channels in the frontend for prospects; it relies on polling and REST writes through the Python server. Direct client DB access is limited to auth.