# 2. System map

## High-level diagram

```mermaid
flowchart TB
  subgraph browser [Browser]
    UI[HTML partials + ES modules]
    TwilioJS[Twilio Voice SDK]
    SupabaseAuth[Supabase JS Auth - Google]
  end

  subgraph app [Python process - server.py]
    WEB[App HTTP :8000 - web.py]
    HOOK[Twilio hooks :8765 - _web/hooks.py]
    DIALER[Dialer session - features/dialer.py]
    CRM[ProspectStore - features/prospects.py]
    MET[Metrics - features/metrics.py]
  end

  subgraph storage [Persistence]
    LOCAL[(crm_data JSON + metrics.json)]
    SB[(Supabase Postgres)]
  end

  subgraph external [External services]
    TW[Twilio Voice + webhooks]
    OAI[OpenAI API]
    CART[Cartesia TTS]
    BR[AI media bridge WebSocket]
  end

  UI -->|REST /api/*| WEB
  UI --> TwilioJS
  UI --> SupabaseAuth
  SupabaseAuth -->|JWT Bearer| WEB
  WEB --> DIALER
  WEB --> CRM
  WEB --> MET
  DIALER --> CRM
  DIALER --> MET
  CRM --> LOCAL
  CRM --> SB
  MET --> LOCAL
  MET --> SB
  TW -->|POST /hooks/...| HOOK
  HOOK --> DIALER
  DIALER --> TW
  BR -->|/api/ai-voice/*| WEB
  DIALER --> BR
  BR --> OAI
  BR --> CART
```

## Connection summary

| From | To | Protocol | Purpose |
|------|-----|----------|---------|
| Browser | `127.0.0.1:8000` | HTTP | SPA shell, static files, JSON API |
| Browser | Twilio | WebRTC + token from `/api/voice-token` | Human agent microphone/earpiece |
| Browser | Supabase Auth | HTTPS | Google OAuth; access token sent as `Authorization: Bearer` |
| Twilio | `127.0.0.1:8765` (exposed as HTTPS via `PUBLIC_BASE_URL`) | HTTP POST | Call status, TwiML, AMD, transcripts |
| AI bridge (optional) | App | HTTP + WebSocket | Stream audio; callbacks on `/api/ai-voice/*` |
| Python server | Supabase | HTTPS REST + RPC | CRUD on `prospects`, metrics, settings |
| Python server | OpenAI / Cartesia | HTTPS | AI agent replies and TTS (when configured) |

## Two HTTP servers in one process

`server.serve()` starts:

1. **App server** — `APP_HOST`/`APP_PORT` (default `127.0.0.1:8000`) — `web.make_app_handler`
2. **Hook server** — `HOOK_HOST`/`HOOK_PORT` (default `127.0.0.1:8765`) — `_web.hooks.make_hook_handler`

Twilio must reach the **hook** port on a **public HTTPS URL** (`PUBLIC_BASE_URL`), while reps use the **app** port locally or behind the same tunnel.