# 7. Information flow

## Generic read path (UI refresh)

```mermaid
sequenceDiagram
  participant UI as Browser poller
  participant API as web.AppHandler
  participant D as Dialer
  participant CRM as ProspectStore

  loop every 1.5s
    UI->>API: GET /api/live
    API->>D: public_state / live projection
    D->>CRM: snapshot (cached)
    API-->>UI: JSON live state
    UI->>UI: sync-state.js merge
    UI->>UI: render() active tab
  end
```

When `leads_version` in live payload changes, poller also fetches `GET /api/leads` for full table rows.

## Generic write path (user action)

```mermaid
sequenceDiagram
  participant UI as Feature JS
  participant API as web.AppHandler
  participant H as Route handler
  participant D as Dialer / CRM

  UI->>API: POST /api/... JSON + Bearer token
  API->>API: open_account → resolve_account
  API->>H: matched handler
  H->>D: business method
  D->>D: update memory + persist CRM/metrics
  H-->>UI: JSON { state, lead, ... }
  UI->>UI: merge state, render
```

`POST` handlers live in `features/*.py`; `web.AppHandler.do_POST` dispatches based on `match_route` and passes parsed JSON.

## Static assets

`GET /main.js`, `/css/*.css` → `HandlerMixin.serve_static` in `_web/respond.py` with MIME types; no auth.

## Twilio callback path

```mermaid
sequenceDiagram
  participant TW as Twilio
  participant HOOK as hooks.HookHandler
  participant D as Dialer
  participant CRM as ProspectStore

  TW->>HOOK: POST /hooks/{token}/{action}
  HOOK->>D: validate_webhook + handle_webhook
  D->>D: update slots, stage, transcript
  D->>CRM: save lead / call_log on terminal events
  HOOK-->>TW: TwiML or empty response
```

Desk token in URL or `DeskToken` query ties callback to the correct `Dialer` instance (`TokenIndex`).

## CSV import flow

1. UI `POST /api/import` multipart or raw CSV body.
2. `prospects.post_import` → `ProspectStore.add_csv`.
3. Parse via `features/_prospects/csv_import.py`; bump `leads_version`.
4. Optional `post_scan` maintenance via explicit scan endpoint—not automatic on GET.