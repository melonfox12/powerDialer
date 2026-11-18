# 10. Configuration and secrets

All keys are defined in `shared/vocabulary.ENV_KEYS` / `SETTING_DEFAULTS`. Values are read by `shared/config.read_env` from `.env` and process environment. **Never commit real values.**

## Twilio (required for live calls)

| Variable | Purpose |
|----------|---------|
| `TWILIO_ACCOUNT_SID` | Account identifier |
| `TWILIO_AUTH_TOKEN` | Legacy auth token (webhook validation, some REST) |
| `TWILIO_API_KEY` | API key SID for capability tokens |
| `TWILIO_API_SECRET` | Secret for API key |
| `TWILIO_TWIML_APP_SID` | TwiML App for browser/client voice |
| `PUBLIC_BASE_URL` | HTTPS base Twilio calls back to (hook port exposed via tunnel) |

## Supabase (optional — enables cloud storage + Google login)

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL` | Project HTTPS URL |
| `SUPABASE_SECRET_KEY` or `SUPABASE_SERVICE_ROLE_KEY` | Server-side REST (service role JWT) |
| `SUPABASE_ANON_KEY` or `SUPABASE_PUBLISHABLE_KEY` | Browser auth config (`GET /api/auth/config`) |

If URL and service key are both set, local JSON CRM is **not** used for signed-in users.

## AI voice

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | LLM turns for AI agents |
| `AI_LLM_MODEL` | Model name (default `gpt-4o-mini`) |
| `CARTESIA_API_KEY` | TTS |
| `CARTESIA_VOICE_ID` | Voice selection |
| `CARTESIA_TTS_MODEL` | Default `sonic-3.6` |
| `AI_VOICEMAIL_DROP` | Boolean string — leave VM vs hang up |
| `AI_VOICEMAIL_MESSAGE` | Text played or spoken on VM |
| `AI_BRIDGE_APP_URL` | App URL bridge calls (default local 8000) |
| `AI_BRIDGE_SECRET` | HMAC/shared auth for bridge HTTP |
| `AI_BRIDGE_EMBEDDED` | `true` to start bridge inside `server.serve` |
| `AI_BRIDGE_HOST` / `AI_BRIDGE_PORT` | WebSocket bind (default `0.0.0.0:8766`) |

Sidecar process also reads `AI_BRIDGE_APP_URL`, `AI_BRIDGE_SECRET`, `AI_BRIDGE_HOST`, `AI_BRIDGE_PORT` in `scripts/ai_media_bridge.py`.

## Dialer UX / session

| Variable | Purpose |
|----------|---------|
| `OPENING_SCRIPT` | JSON string of opener lines (parsed in `read_env`) |
| `PIPELINE_CUSTOM_STEPS_JSON` | Custom pipeline columns |
| `DAILY_GOAL_MINUTES` | Talk-time goal |
| `DAILY_CONVERSATION_GOAL` | Conversation count goal |
| `DAILY_GOAL_WEEKLY_STEP_MINUTES` | Auto-increment weekly |
| `DAILY_GOAL_ANCHOR` | Date anchor for weekly step |

Additional tunables (calling hours, sounds, session goal, etc.) are in `SETTING_DEFAULTS` in `shared/vocabulary.py` — persisted via Settings UI to `.env` and/or `dialer_settings`.

## Network (code constants, not env)

| Constant | File | Default |
|----------|------|---------|
| `APP_HOST` / `APP_PORT` | `shared/config.py` | `127.0.0.1:8000` |
| `HOOK_HOST` / `HOOK_PORT` | same | `127.0.0.1:8765` |

## Paths (local data)

| Constant | Default |
|----------|---------|
| `CRM_PATH` | `<repo>/crm_data` |
| `METRICS_PATH` | `<repo>/metrics.json` |
| `ENV_PATH` | `<repo>/.env` |