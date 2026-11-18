# 12. Glossary

| Term | Meaning |
|------|---------|
| **Account** | `features/accounts.Account` — bundles CRM, metrics, dialer for one storage context |
| **Active lead** | Lead currently in wrap-up or live conversation in dialer UI |
| **AMD** | Answering Machine Detection — Twilio `AnsweredBy` param |
| **AppRuntime** | Process-singleton wiring for storage and user sessions |
| **Bearer token** | Supabase JWT access token in `Authorization` header |
| **Bump metrics** | Increment counters in `MetricsStore`, not CRM-derived |
| **Call log** | `call_log[]` on a lead — one entry per completed attempt |
| **Capability token** | Twilio JWT for browser Device (`/api/voice-token`) |
| **CRM** | Prospect database and UI table |
| **Desk token** | Secret token embedding in Twilio webhook URL to find `Dialer` |
| **Disposition** | In-call outcome button mapping to status (`STATUS_CALL_OUTCOME`) |
| **Dial archive** | Historical dial metadata store (`dial_archive` table) |
| **Dial cap** | Rule closing leads after repeated no-connect dials (`dial_policy`) |
| **Dial pool** | Leads eligible for auto-dial given status + timezone + industry filters |
| **Dial record** | Saved snapshot of a dialing session strip (`dial_records`) |
| **DIAL_POOL_STATUSES** | Usually `new` and `contact_engaged` |
| **FeatureContext** | `web.FeatureContext` — helpers for settings routes |
| **Hook server** | HTTP server on port 8765 for Twilio only |
| **In-flight** | Parallel outbound calls not yet resolved to single live connect |
| **Lead / prospect** | Same entity — JSON row in CRM |
| **Live state** | `GET /api/live` payload without heavy `pool` array |
| **Pipeline step** | Kanban column key on lead (`pipeline_step`) |
| **Pool** | Callable leads list in API / caller pool tab |
| **Power dialer** | Multi-line dial until human answers |
| **Projection** | Building API JSON from internal dialer state |
| **PUBLIC_BASE_URL** | Twilio-facing HTTPS origin |
| **RLS** | Supabase row-level security (policies in schema.sql) |
| **Service role** | Supabase key with server-side full access |
| **Session stats** | Per dialing session counters (`session_stats` in state) |
| **Stage** | High-level dialer UI phase (`idle`, `dialing`, …) |
| **TokenIndex** | Maps webhook tokens → `Dialer` instances |
| **TwiML** | Twilio XML call control returned from hooks |
| **Vocabulary** | `shared/vocabulary.py` constants shared with browser |
| **Wrap-up** | Post-call phase before auto-advance to next lead |
| **AI seat / agent** | Configured AI dialer personality with playbook |

### Abbreviations

| Abbr | Expansion |
|------|-----------|
| API | Application HTTP JSON interface |
| CRM | Customer relationship management (prospects) |
| CSV | Comma-separated import/export |
| JWT | JSON Web Token (Supabase session, Twilio capability) |
| LLM | Large language model (OpenAI) |
| REST | HTTP JSON Supabase PostgREST |
| STT | Speech-to-text |
| TTS | Text-to-speech (Cartesia) |
| UI | Browser dashboard |
| VM | Voicemail |
| WSS | WebSocket Secure (media bridge) |