# DialerApp — Developer Handbook

First-principles guide for programmers who are new to this repository. Read sections in order, or jump via the table below.

**Why this exists:** The app is a single-page CRM plus power dialer. Behavior is spread across a Python HTTP server, Twilio telephony, optional Supabase storage, and a plain-JavaScript frontend with no bundler. This handbook explains *why* those pieces exist before *how* to change them.

## Table of contents

| # | Topic | File |
|---|--------|------|
| 1 | What the app is | [handbook/01-overview.md](handbook/01-overview.md) |
| 2 | System map | [handbook/02-system-map.md](handbook/02-system-map.md) |
| 3 | Folders and files | [handbook/03-folders.md](handbook/03-folders.md) |
| 4 | Tech stack | [handbook/04-tech-stack.md](handbook/04-tech-stack.md) |
| 5 | Core concepts | [handbook/05-concepts.md](handbook/05-concepts.md) |
| 6 | Data model | [handbook/06-data-model.md](handbook/06-data-model.md) |
| 7 | Information flow | [handbook/07-information-flow.md](handbook/07-information-flow.md) |
| 8 | End-to-end user traces | [handbook/08-user-traces.md](handbook/08-user-traces.md) |
| 9 | Background & realtime | [handbook/09-background-realtime.md](handbook/09-background-realtime.md) |
| 10 | Configuration & secrets | [handbook/10-configuration.md](handbook/10-configuration.md) |
| 11 | API & function reference | [handbook/11-api-reference.md](handbook/11-api-reference.md) |
| 12 | Glossary | [handbook/12-glossary.md](handbook/12-glossary.md) |

## Related docs

- `docs/ARCHITECTURE.md` — HTTP JSON contract (keys align with `shared/api_contract.py`)
- `docs/AI_VOICE.md` — AI dialer voice pipeline
- `docs/supabase/schema.sql` — Postgres tables for cloud mode
- `docs/PROGRESS.md` — annotation batch tracker
- `docs/ISSUES.md` — known oddities found during handbook/annotation work

## Quick start

```bash
python dialer.py   # or: python server.py
```

Open `http://127.0.0.1:8000`. Without Supabase keys, CRM data lives under `crm_data/` (local JSON). With Supabase configured, sign in with Google in the browser (`static/features/auth.js`).