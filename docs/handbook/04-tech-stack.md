# 4. Tech stack

## Backend

| Piece | Where used | Role |
|-------|------------|------|
| **Python 3** stdlib | Throughout | `http.server.ThreadingHTTPServer`, `threading`, `json`, `pathlib` |
| **Twilio** (`requirements.txt`) | `features/_dialer/twilio.py` | Outbound calls, TwiML, capability tokens, webhook signature validation |
| **tzdata** | Timezone names in vocabulary + pool filters | IANA zone data on Windows |
| **websockets** | `features/ai_media_bridge.py`, bridge script | AI audio streaming |

There is **no Flask/FastAPI**; routing is a hand-rolled list in `web.all_routes()`.

## Frontend

| Piece | Role |
|-------|------|
| **Native ES modules** | `import`/`export` in browser; files served as static |
| **Plain CSS** | Design tokens in `01-tokens.css`, Linear theme overrides in `css/linear/` |
| **No React/Vue** | DOM updates via render functions registered in `static/_core/registry.js` |
| **Twilio Voice JS** | Loaded when human browser voice is required (`requires_browser_voice` in state) |
| **Supabase JS** (browser) | Loaded for Google sign-in when `GET /api/auth/config` returns `google: true` |

## Data stores

| Mode | Technology | Location |
|------|------------|----------|
| Local dev | JSON files | `crm_data/` (prospects), `metrics.json`, dial record side files |
| Cloud | Supabase Postgres | Tables in `docs/supabase/schema.sql`; server uses **service role** key |

## External APIs

| Service | Config keys | Used by |
|---------|-------------|---------|
| Twilio | `TWILIO_*`, `PUBLIC_BASE_URL` | Dialing, webhooks, browser token |
| Supabase | `SUPABASE_URL`, `SUPABASE_SECRET_KEY` or `SERVICE_ROLE`, `SUPABASE_ANON_KEY` | Auth (browser), storage (server) |
| OpenAI | `OPENAI_API_KEY`, `AI_LLM_MODEL` | AI agent dialogue |
| Cartesia | `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID` | AI TTS |
| AI bridge | `AI_BRIDGE_*` | Optional embedded or sidecar WebSocket bridge |

## Testing & tooling

| Tool | Role |
|------|------|
| `unittest` | `tests/` — HTTP, dialer flows, vocabulary |
| `git` | Version control; annotation verification diffs against `HEAD` |