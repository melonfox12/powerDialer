# AI autonomous voice

## Runtime flow

1. Start **AI Dialer** seat → requires `AI_BRIDGE_WSS_URL` + `AI_BRIDGE_SECRET` (hard fail otherwise).
2. On human pickup → Twilio **Media Stream** to bridge WSS; bridge forwards inbound mulaw → Whisper STT → LLM → Cartesia TTS → bridge plays outbound mulaw.
3. Twilio live transcription is **off** while the media stream is active (dedupe).
4. On hangup → LLM suggests CRM status when there was dialogue; otherwise existing `finalize_agent_call` fallback.

## Settings (account / env via Settings save)

| Key | Purpose |
|-----|---------|
| `AI_BRIDGE_WSS_URL` | Public `wss://` URL Twilio can reach (tunnel + bridge) |
| `AI_BRIDGE_APP_URL` | Where bridge polls dialer (default `http://127.0.0.1:8000`) |
| `AI_BRIDGE_SECRET` | Shared header `X-AI-Bridge-Secret` |
| `OPENAI_API_KEY` / `AI_LLM_MODEL` | STT (Whisper) + turn-taking |
| `CARTESIA_API_KEY` / `CARTESIA_VOICE_ID` | Spoken audio |
| `AI_VOICEMAIL_DROP` | `true` → leave short Twilio `Say` on voicemail AMD |
| `AI_VOICEMAIL_MESSAGE` | Optional custom voicemail line (env / `.env`) |

## Run the bridge

**Option A — embedded** (single process): set `AI_BRIDGE_EMBEDDED=true` in Settings (or `.env`) and restart `server.py`. WebSocket listens on `0.0.0.0:8766` by default (`AI_BRIDGE_PORT` / `AI_BRIDGE_HOST`).

**Option B — separate process:**

```bash
set AI_BRIDGE_SECRET=your-secret
set AI_BRIDGE_APP_URL=http://127.0.0.1:8000
python scripts/ai_media_bridge.py
```

Expose `ws://127.0.0.1:8766` as HTTPS/WSS (e.g. ngrok) and set `AI_BRIDGE_WSS_URL` to that public URL.

## Bridge API (shared secret)

- `GET /api/ai-voice/stream-sync?session=…` — outbound mulaw chunks (base64)
- `POST /api/ai-voice/inbound` — inbound mulaw batch from bridge
- `POST /api/ai-voice/stream-started` / `stream-stopped` — stream lifecycle

## Optional

- End a call from the prompt with `[END_CALL]` in the model reply.
- Without Cartesia keys, transcript still updates; prospect hears silence until TTS is configured.
- Listen-in is disabled in AI mode (server-side audio only).
