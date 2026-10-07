# powerDialer — architecture audit

Audited commit `4607dfa` (2026-10-06 20:40, "latest updfates"). The repo is 49 commits old. Everything here was read-only: the repo was copied to a scratch directory on your machine (`~/audit`, `~/run`, outside the connected folder), and every test run and probe ran against those copies. Nothing in `powerDialer/` was written to.

Labels: **VERIFIED** means I confirmed it in code, by grep, or by running it. **INFERRED** means it is likely but unconfirmed, and I say what would confirm it. **UNKNOWN** means I couldn't determine it.

---

## 1. Executive summary

1. **The most expensive problem is that no one module owns the dialer's state machine.** `DialerState` has 36 attributes. Six of them (`active`, `pending_outcome`, `in_flight`, `paused`, `agent_ready`, `running`) control what happens next, and four or five different files write each of them (`call_events.py`, `ended.py`, `pickup.py`, `queue.py`, `calls.py`, `outcomes.py`). To answer "when does the dialer go to wrap-up?" you have to read five files. Every change to call flow is expensive and risky for this reason.
2. **Business rules have copies, or have no owner, and several of these are already live bugs.** The calling-hours setting validates, saves and displays, but nothing enforces it (removed in `70366cb`). A failed Supabase write leaves a "Do not call" status in the server's cache, so the UI shows a status that was never saved. Metric increments are read-modify-write over HTTP, so concurrent increments lose counts. Twilio secrets are sent to the browser in plaintext. In local mode the settings endpoint accepts a cross-site `text/plain` POST that rewrites the Twilio credentials and webhook URL. I confirmed each of these by running it (§2).
3. **Concepts are spread across many files.** Each traced feature touches 6–33 files, with scatter scores of 2.0–3.7× the minimum a clean design would need (§4). Settings are the clearest case: the same nine keys are mapped by hand in five places.
4. **The old 150-line rule left fragmentation behind.** The 20 dialer JS files average 53 lines. `Dialer` has 23 one-line forwarders and `ArcadeSensoryController` has 23 more. Tests are assembled from `Part1..Part4` mixins. 140 CSS selectors are defined in more than one file (`.dialer-run-panel` in 7). The rule even reached the data format: local prospects are written as 150-line JSON shards (`PART_LINE_LIMIT = 150`).
5. **Repo hygiene works against agents.** The suite is red (2 of 41 tests fail, both from the last commit). There are 16 ghost package directories that hold only `__pycache__`, and `__pycache__` is tracked in git. The two architecture docs total 835 lines and reference 185 paths that don't exist. CRLF files with no `.gitattributes` show up as 140 fully modified files in any non-Windows checkout.
6. **What's already good, and should be left alone:**
   - Neither Python nor JS has an import cycle. Python layering is mostly correct, and storage modules don't import the dialer.
   - Twilio REST calls and signature checking are isolated in one module, and webhook signatures are checked on every callback.
   - Per-call tokens route webhooks to the right tenant.
   - The browser builds DOM with `textContent`. The only `innerHTML` writes are numeric SVG.
   - `shared/vocabulary.py` is injected into the page as JSON.
   - `SupabaseClient` is a clean, well-behaved adapter.
   - The CSV header heuristics are cohesive.
   - The tests run in about 2 seconds, and `test_http.py` locks the API payload key sets.
7. The fix is not another big move. It's an ordered sequence: make the suite green and delete the dead files, fix the six correctness and security bugs behind tests, give settings and the dialer state machine one owner each, and only then consolidate the frontend and CSS (§8).

**Where your context was wrong (rule 7):**

- There is no `.venv/` or `node_modules/` in the folder.
- `__pycache__` *is* tracked in git: 10 `.pyc` files, including `plivo_calls`, a leftover from an earlier Plivo integration. There are 143 `.pyc` files on disk.
- `Claude outputs/` is not just noise. It's tracked, and a test depends on it (`tests/test_transcript_storage/part_1.py:110`).
- Local JSON is not a *fallback* for Supabase. The backend is chosen once at startup (`features/accounts.py:32-51`), and there is no runtime failover.
- The 150-line rule was enforced by a script (`09e1122`: `raise SystemExit("files still over 150 lines")`), not by a rules file. `AGENTS.md` now says "up to ~500 lines is fine" (`AGENTS.md:3`, added in `4607dfa`).

---

## 2. Critical issues (live bugs, data integrity, security, compliance)

| # | Issue | Evidence | Label |
|---|---|---|---|
| C1 | **The calling-hours guardrail does nothing.** `within_calling_window` is defined (`features/_dialer/session_stats.py:105`) and tested (`tests/test_dialer_session/part_1.py:47-50`), but no production code calls it. `fill_slots` picks any `new` lead (`features/_dialer/slots.py:21-25`). The filter was removed from `slots.py` and the state projection in commit `70366cb` ("working dialer", 2026-10-05), and `docs/supabase/setup.md:23` now says "Calls are not blocked by local time". The Settings UI still offers "Calling starts/ends (local hour)" (`static/features/settings.html:17-18`), and the server still validates and persists those hours (`features/settings.py:21-22,31`). | Probe: an Eastern lead at 20:51 local with a 08–09 window → `within_calling_window` = False → `fill_slots` launched `+12025550100`. | VERIFIED (that it's a no-op). Whether the removal was intended is open question Q1. TCPA-style calling-hour compliance risk. |
| C2 | **A failed Supabase write leaves the cache diverged, and "Do not call" can silently revert.** `ProspectStore.set_status` changes the cached lead before writing (`features/prospects.py:67-80`), and `SupabaseBackend._write` raises after the change (`features/_prospects/backend_supabase.py:43-52`). Same pattern in `append_transcript` and `append_call_log` (`prospects.py:97-102,120-124`). | Probe: PATCH returns 503 → error is raised → `snapshot()` still shows `do_not_call`. After a restart the lead loads as `new` from Supabase and auto-dial can pick it. | VERIFIED (divergence). The re-dial after restart is INFERRED from the `_fetch` path (`backend_supabase.py:27-41`). |
| C3 | **Metric increments lose updates.** `SupabaseMetricsStore._increment` does a GET, then a POST of `current + amount` (`features/metrics.py:110-121`). | Probe: 5 concurrent `bump("dials")` calls against a fake client with 50 ms latency stored `1`, not `5`. | VERIFIED |
| C4 | **Twilio secrets reach the browser.** `settings_state` returns `auth_token` and `api_secret` in plaintext (`features/settings.py:49,51`), even though it also computes `has_auth_token` and `has_api_secret`. `settings.js:9,11` writes them into inputs, and they sit in `state.settings` until the next poll. | Probe: `GET /api/settings` → `"auth_token": "tok"`. | VERIFIED |
| C5 | **Local mode is open to CSRF.** The server ignores Content-Type (`_web/respond.py:50-56`), checks neither Origin nor Host (grep found no `Origin`, `Host`, `Access-Control` or `csrf` anywhere in the Python code), and local mode has no auth (`features/accounts.py:123-124`). | Probe: POST `/api/settings` with `Content-Type: text/plain` and `Origin: https://evil.example` → 200, and `.env` was rewritten with `PUBLIC_BASE_URL=https://attacker.example` and new Twilio credentials. A browser sends this as a "simple" no-cors request. DNS rebinding could also read C4's secrets. | VERIFIED server-side. The cross-site delivery is standard browser behavior and wasn't exercised in a browser. |
| C6 | **Signed-in users inherit the shared `.env` Twilio credentials.** Every signed-in session is built with the same `ENV_PATH` (`features/accounts.py:80`), and `values()` merges `read_env(.env)` under the account values (`features/settings.py:40-41`). `read_env` also falls back to `os.environ` (`shared/config.py:44-45`). Saving settings then copies the merged values into that user's row (`settings.py:99-100`). | Probe: `.env` holds `TWILIO_AUTH_TOKEN=shared-secret-token`, and a fresh signed-in user B's `settings_state()` returns `ACshared` / `shared-secret-token`. This contradicts setup.md: "Each Gmail account only sees its own data." | VERIFIED |
| C7 | **The dialer lock is held during network and disk I/O.** `fill_slots` holds `state.lock` (`slots.py:12-29`) and calls `_new_call`, which calls `metrics.bump` and `save_session` (`calls.py:118-123`). On Supabase that is 4–5 HTTP round trips. The same pattern appears in `start` (`queue.py:86`), `_pickup` (`pickup.py:20-23`), `_call_ended` (`ended.py:37-43`) and `choose_outcome` (`outcomes.py:31-33`). Webhooks and `/api/live` polls for that user block meanwhile. | Probe: a 1 s fake metrics store made `public_state()` block for **1.40 s**. | VERIFIED |
| C8 | **The test suite is red.** `tests/test_manual_prospect.py:5` imports `crm_store.CRMStore`, which was deleted in phase 5. `static/js/controllers/new-prospect.js` imports 6 missing modules and 13 missing DOM ids, which fails `test_static`. All three files came from `4607dfa` (author `max-pc`, a different machine), re-introducing old-architecture code after the refactor. `crm_store/leads/manual.py` imports deleted modules too. | `Ran 41 tests … FAILED (failures=1, errors=1)` | VERIFIED |
| C9 | **Supabase without an anon key makes the app unusable.** When Supabase is configured, `local` is set to `None` (`accounts.py:39`). Without an anon key `resolve_account` returns `(None, None)` (`accounts.py:122-124`), and every `/api/*` call returns 401 "Sign in with Google" (`web.py:139-141`) while the UI shows no Google button. | Probe: `resolve_account → (None, None)` | VERIFIED (resolver). The UI symptom is VERIFIED by reading `auth.js:50-53` and `api.js:46-50`. |
| C10 | **Supabase import reports a wrong total.** `info["total"] = len(leads) + len(additions)` runs after `leads.extend(additions)` (`backend_supabase.py:120-122`). | Probe: 2 rows imported → Supabase total 4, local total 2. | VERIFIED. The earlier plan saw this and chose not to fix it (`docs/ARCHITECTURE_MAP.md:661`). |
| C11 | **Settings are written to Supabase twice per save.** `FeatureContext.save_posted_settings` calls `Dialer.save_settings`, which calls `settings_saver` → `persist_settings`, and then calls `persist_settings` again (`web.py:238-241`, `features/dialer.py:96-103`). | Probe: 2 `dialer_settings` upserts per POST. | VERIFIED |
| C12 | **Local shard writes aren't atomic as a set.** `write_lead_parts` replaces `part-NN.json` one file at a time and then unlinks the leftovers (`backend_local.py:44-58`). A crash partway through leaves a mix of old and new shards, so leads can be duplicated or lost. | Code path | INFERRED. Confirm by killing the process between shard writes in a copy. |
| C13 | **The debug log redaction has gaps.** `TWILIO_AUTH_TOKEN=abc` and `TWILIO_API_SECRET=zz` pass through unredacted, and `Authorization: Bearer eyJabc` keeps the token (`shared/_infra/files.py:12-14`). The regex needs a word boundary, and `_` is a word character. | Probe output | VERIFIED. Exposure depends on what gets logged (tracebacks, client debug). |
| C14 | **The migration script writes rows no user can see.** `scripts/migrate_to_supabase.py` never sets `user_id`, while every signed-in read filters on `user_id=eq.<uid>` (`backend_supabase.py:18-22`). | grep: no `user_id` in the script | VERIFIED (missing field). That users can't see migrated rows is INFERRED; confirm by migrating and signing in. |

---

## 3. Phase 0 — metrics

All counts exclude `.git`, `__pycache__`, `Claude outputs`, `.venv` and `node_modules`. Scripts are in the appendix.

| Metric | Value |
|---|---|
| Python | 62 files, 5,675 lines (median 70; 14 files under 20 lines, of which 8 are empty `__init__.py`; 14 over 150; 1 over 300) |
| JavaScript | 57 files, 3,630 lines (median 61; 7 under 20; 1 over 150; 0 over 300) |
| CSS | 14 files, 1,731 lines (median 119.5) |
| HTML | 7 files, 762 lines (379 of them are the `docs/page-before.html` test snapshot) |
| All code (py/js/css/html) | 140 files, 11,798 lines. Median 69, mean 84. **123 of 140 (88%) are ≤150 lines**: the old rule is still visible. 22 are under 20 lines. 2 are over 300. Largest: `tests/test_http.py` at 314. |
| Folders with files | 30. Max depth 4 (`static/features/_dialer/_voice`). |
| Folders with only 1–2 code files | 6: `shared/_infra`, `_web`, `static/features/_performance`, `static/js/controllers`, `crm_store/leads`, `docs` |
| Ghost directories (only `__pycache__`) | **16**: `core`, `routes`, `routes/ui`, `supabase_store/{,client,leads,transcripts}`, `twilio_calls/{,client,dialer,lifecycle,lifecycle/queue,settings,token,transcript,webhooks}`. Also 143 `.pyc` files on disk, 10 of them tracked. |
| Python import graph | 62 nodes, 158 edges, **0 cycles** (Tarjan SCC) |
| JS import graph | 57 nodes, 219 edges, **0 cycles**. 1 orphan (`static/js/controllers/new-prospect.js`). 6 imports point at missing files. |
| Python hubs (fan-in) | `shared.infra` 13, `features._dialer.session_stats` 11, `shared.vocabulary` 11, `features.prospects` 10, `features.dialer` 8 (with **16 fan-out**), `features._dialer.calls` 8 |
| JS hubs (fan-in) | `_core/format.js` 37, `_core/state.js` 34, `core.js` 19 (barrel), `_core/notify.js` 16, `_core/api.js` 13. Fan-out: `features/dialer.js` 16, `core.js` 10, `_dialer/bindings.js` 10. |
| Re-export / aggregator files | `shared/infra.py` (pure re-export, 11 non-blank lines), `static/core.js` (barrel plus three registries, 66 lines), `static/features/dialer.js` (wiring plus re-exports), `static/features/prospects.js` (registration plus re-exports, 11 lines), `tests/test_dialer_session/__init__.py` and `tests/test_transcript_storage/__init__.py` (mixin assemblers) |
| Forwarding-only methods | `Dialer`: 23 of 24 methods are `return part.fn(self, …)` (`features/dialer.py:20-93`); 7 of them are called only by tests. `ArcadeSensoryController`: 23 forwarders (`static/features/arcade.js:17-41`). `ProspectStore`: 7 of 15. |
| Mixed import style | 13 JS files import both the `core.js` barrel and `_core/*` directly |
| CSS duplication | 733 distinct selectors. **140 are defined in more than 1 file, 39 in 3 or more.** `.dialer-run-panel` and `main` are each in 7 files. |
| Tests | 44 test functions, 41 collected, 2 failing. Runtime about 2.1 s. |
| Line endings | 138 tracked files are LF in the index and CRLF in the working tree, with no `.gitattributes`. A fresh copy without `core.autocrlf` shows **140 files as modified** (for example `web.py` shows 498 changed lines). |

**Entry points and runtime boundaries (VERIFIED):**

- **Servers:** the app server on `127.0.0.1:8000` and the Twilio hook server on `127.0.0.1:8765`, which runs on its own thread (`shared/config.py:13-16`, `server.py:22-27`). `dialer.py` is an 8-line launcher.
- **Threads and timers:**
  - Per-call create threads: `calls.py:26`
  - Hangup threads: `calls.py:92`, `queue.py:196`, `call_events.py:116,146`
  - `fill_slots` threads: `call_events.py:50,85`
  - Auto-advance `Timer`: `timing.py:19`
  - 60 s calling-window `Timer`: `slots.py:42`. It still runs every minute while dialing but only refills slots.
- **Browser:**
  - 1.5 s poll of `/api/live`, plus `/api/state` when the leads version changes: `poller.js:33-36,67`
  - Metrics fetched every 15 s: `poller.js:52`
  - 1 s call timer: `timer.js:21`
- **External services:**
  - Twilio REST (`twilio_api.py:15`) and webhooks
  - Twilio Voice SDK and supabase-js from jsDelivr (`static/shell.html:25-26`)
  - Supabase REST and Auth
  - Google Fonts (`shell.html:10`)
- **Configuration outside the repo:**
  - `.env`
  - Twilio console: the TwiML App's Voice URL must be `{PUBLIC_BASE_URL}/hooks/voice`. That is INFERRED from `_web/hooks.py:28,59` and `twilio_api.py:123`. It isn't documented anywhere in the repo (VERIFIED by grep).
  - A public HTTPS tunnel to port 8765 (only mentioned in a `print`, `server.py:30`)
  - Supabase dashboard (Google provider, redirect URLs) and a manual run of `schema.sql` (`docs/supabase/setup.md`)

**Noise an agent will trip over (all VERIFIED):**

- The 16 ghost directories and tracked `.pyc` files above.
- `call_log.csv` is tracked even though `.gitignore:56` ignores it, and no code references it.
- `debug-session.log` is truncated on every start (`files.py:21-26`).
- The suite is red (C8).
- `docs/ARCHITECTURE_MAP.md` and `docs/FRONTEND_MAP.md` (835 lines) are a phase-by-phase plan, not a map. 140 of 236 and 45 of 116 of the paths they name don't exist, and their planned phase 7 (`check_architecture.py`, `test_architecture.py`, `tests/test_dialer.py`, `test_prospects.py`, `test_accounts.py`) never happened.
- `scripts/check_js_urls.py` was meant to be deleted and nothing references it.
- `tests/test_http.py:98-99` *writes* `docs/page-before.html` if it's missing, and every markup change requires regenerating that "doc".
- A test fixture lives in `Claude outputs/`.
- There's no README, and the Twilio setup is undocumented.

---

## 4. Phase 1 — feature map

The traces were done by hand while reading the code. The counts are computed from the traces by `features.py` in the appendix.

- **Static:** a call go-to-definition can follow.
- **Forwarding:** a hop through a file or method that only forwards.
- **Hidden:** URL strings, DOM ids, events, registries, threads and timers, injected untyped collaborators, `getattr`/`hasattr`, Twilio console configuration, polling.
- **Min:** the number of files a well-structured version would need, with my reasoning in the last column.

| Feature | Files | Folders | Static | Fwd | Hidden | Min | Scatter | Minimum set |
|---|---|---|---|---|---|---|---|---|
| Start dialing session | 33 | 11 | 19 | 7 | 12 | 9 | **3.7** | dialer UI+voice, api client, dialer routes, session service, Twilio adapter, prospect repo, metrics, settings, webhook route |
| Answer / pickup / AMD | 17 | 7 | 6 | 3 | 8 | 6 | 2.8 | webhook route, call-events, metrics, projection, dialer view, stage view |
| Live transcription | 11 | 8 | 2 | 1 | 8 | 5 | 2.2 | transcription handler, prospect repo, projection, monitor, transcript view |
| Disposition after a call | 19 | 8 | 8 | 1 | 10 | 6 | 3.2 | disposition UI, api, route, outcome service, prospect repo, metrics |
| Hangup / skip / pause / advance | 12 | 5 | 8 | 1 | 3 | 5 | 2.4 | controls UI, api, route, session service, Twilio adapter |
| Manual dial from a row | 11 | 7 | 8 | 2 | 1 | 5 | 2.2 | menu, dialer controller, api, route, session |
| CSV import | 13 | 9 | 5 | 4 | 3 | 4 | 3.2 | import UI, route, prospect service, csv module |
| CSV export | 6 | 4 | 2 | 2 | 1 | 3 | 2.0 | route, repo, csv module |
| Manual add prospect | 11 | 9 | 4 | 2 | 4 | 4 | 2.8 | form, route, service, lead factory |
| Status change / delete | 10 | 6 | 3 | 1 | 5 | 4 | 2.5 | table UI, api, route, service |
| Settings view/save | 12 | 8 | 8 | 2 | 4 | 4 | 3.0 | settings UI, route, service, repo |
| Performance metrics | 14 | 9 | 4 | 0 | 9 | 4 | **3.5** | recorder, route/store, view, charts |
| Google sign-in / tenant | 9 | 7 | 6 | 0 | 2 | 4 | 2.2 | auth UI, api, resolver, Supabase client |
| Session goal / summary | 6 | 4 | 3 | 0 | 2 | 3 | 2.0 | session service, metrics, session UI |

**Ordered file lists (call order; the hidden mechanism in brackets):**

- **Start dialing session:**
  - `main.js` → `features/dialer.js` (re-export) → `_dialer/bindings.js` → [#startButton] `_dialer/session.js` → `_core/api.js` → [URL `/api/start`] `web.py` → `features/accounts.py` → `features/dialer.py` (route, then `Dialer.start` forwarder) → `_dialer/queue.py` → `_dialer/calls.py`
  - → [injected `state.crm`] `features/prospects.py` → `_prospects/backend_local.py` or `backend_supabase.py` (chosen at runtime)
  - → `features/settings.py` → `shared/config.py` (reads `.env`) → `shared/vocabulary.py` → `_dialer/twilio_api.py` → `_dialer/session_stats.py` → [injected + `hasattr`] `features/metrics.py` → `_dialer/state.py` → [Timer] `_dialer/slots.py` → `_dialer/projection.py` → [mixin] `_web/respond.py`
  - Browser: `_dialer/connect.js` → `_voice/connect.js` → [URL `/api/voice-token`] `web.py` → `features/dialer.py` → `_voice/devices.js` → `_dialer/card.js`
  - Twilio: [Twilio Device + TwiML App Voice URL in the console + `CallToken`] `_web/hooks.py` → `features/dialer.py` → `_dialer/call_events.py` → [Thread] `slots.fill_slots` → [Thread] `calls._create_call`
  - Rendering: `_core/state.js` → `core.js` → `_core/render.js` → [registry] renderers
- **Answer / pickup / AMD:** [Twilio POST `/hooks/{token}/{answer|status|machine}`] `_web/hooks.py` → [TokenIndex registry] `twilio_api.py` → `features/dialer.py` (2 forwarders) → `call_events.py` → [string action] `_call_events/pickup.py` → `session_stats.py` → [injected] `metrics.py` → `calls.py` → `_call_events/transcript.py` (TwiML) → [1.5 s poll] `_dialer/poller.js` → `web.py` → `projection.py` → [registry] `render-dialer.js` → `stage.js` → `monitor.js` → [mutable `stageEffects`] `effects.js` → `arcade.js`
- **Live transcription:** `_call_events/transcript.py` (TwiML `<Start><Transcription>` callback) → [Twilio] `hooks.py` → `dialer.py` → `call_events.py` → `transcript.py` → [injected] `prospects.py` → `backend_*.py` (duck-typed `leads_locked`/`save_locked`) → [poll] `projection.py` → `monitor.js` → `_core/transcript.js` → [`registerTranscriptActions`] `_prospects/transcript.js`
- **Disposition:**
  - [DOM ids, or keyboard 1–5 with an id array] `_dialer/outcomes.js`, `_dialer/keyboard.js` → `_core/time.js` → `api.js` → [URL; handler-identity dispatch at `web.py:187`] `web.py` → `dialer.py post_status` → `Dialer.update_status` → `_dialer/outcomes.py` → `session_stats.py` → `vocabulary.py` → `prospects.py` → `backend_*` → `metrics.py` → `timing.py` → [Timer] `slots.py` → `projection.py`
  - UI effects: `effects.js` → `arcade.js` → `outcome-row.js`
- **CSV import:** [#csvInput] `_prospects/csv.js` → `api.js` → [URL; `web.py:189` passes the raw body only to `post_import`] `web.py` → `respond.py` (`MAX_BODY`) → `prospects.py` → `backend_*` (forwarders) → `_prospects/csv_import.py` → `vocabulary.py` → [`request.ctx.state()` callback] `projection.py` via `Dialer` → `core.js` → `navigation.js`
- **CSV export:** `prospects.html` `<a href>` → `web.py` → `prospects.py` → `backend_*` → `csv_export.py`
- **Manual add prospect:** `_prospects/add-prospect.js` → `api.js` → `web.py` → `prospects.py` → `backend_*` → `csv_import.build_manual_lead` → `vocabulary.py` → `projection.py`. A reader also has to rule out two divergent dead copies: `crm_store/leads/manual.py` and `static/js/controllers/new-prospect.js`.
- **Status change / delete:** `_prospects/rows.js` → [CustomEvent `"prospect-status"`] `_prospects/records.js` → `api.js` → `web.py` (DELETE is a hard-coded prefix branch, `web.py:219-220`) → **`features/dialer.py post_status`** (the dialer owns the prospect-status route) → `outcomes.py` → `prospects.py` → `backend_*` → `projection.py`
- **Settings:** `settings.js` → `core.js` → `api.js` → `web.py` → `features/settings.py post_settings` → [`request.ctx` calls back into `web.py`'s `FeatureContext`] → `features/dialer.py save_settings` → `settings.py` → `config.write_env` → [`settings_saver` lambda + `getattr`] `accounts.py` → `settings.save_app_settings` → `_infra/supabase.py` → `vocabulary.py`. Then [the poll overwrites `state.settings` with a different shape] `projection.py`, and `arcade.js syncControls`.
- **Performance metrics:**
  - Read path: [15 s throttle inside the 1.5 s poll] `poller.js` → `api.js` → `web.py` → `metrics.py get_metrics` → [`account.metrics` chosen at runtime] `accounts.py` → `core.js` → [registry] `performance.js` → `charts.js`
  - Writes happen elsewhere, through `_bump`, in `session_stats.py`, `calls.py`, `ended.py`, `pickup.py` and `outcomes.py`.
- **Google sign-in:** `main.js` → `auth.js` → `web.py` (hard-coded `/api/auth/config` branch) → `accounts.resolve_account` → `_infra/supabase.auth_user` → `config.PUBLIC_API_PATHS` → [`setUnauthorizedHandler`] `api.js` → `dialer.js` (`refreshState`) → `settings.js`
- **Session goal / summary:** [registry] `session-goal.js` → `summary.js`. The summary dialog is bound by **`_prospects/transcript.js:44`** (`bindDialogs` calls the dialer's `bindSessionSummary`). Then `queue.stop` → `session_stats.session_summary` → `metrics.recent_sessions` (guarded by `hasattr`, `queue.py:204`).

**Inverse map: files that serve three or more features (VERIFIED from the traces):**

| File | Features | Verdict |
|---|---|---|
| `web.py` | 12 | Legitimate HTTP hub, but also holds `FeatureContext` callbacks and handler-identity special cases |
| `static/_core/api.js` | 10 | Legitimate infrastructure hub |
| `features/dialer.py` | 9 | **Dumping ground.** Dialer routes, a 23-method facade, settings orchestration (`save_settings`), and the *prospect* status route. |
| `features/_dialer/projection.py` | 9 | **God view.** Every poll builds leads, pool, timezone groups, session stats and parsed settings, and reads `.env` from disk (`projection.py:65`). `/api/live` then discards leads and pool (`projection.py:101-105`). |
| `features/prospects.py` + both backends | 7 | Expected for a repository, but the rules are split across the store and both backends (§6) |
| `features/_dialer/session_stats.py` | 5 | Mixed: stage derivation, disposition mapping, session counters, unused calling-hours math, and metric I/O wrappers |
| `features/metrics.py`, `shared/vocabulary.py` | 5 | Fine |

**Verdict:** the code is organized by feature at the top level (`features/{dialer,prospects,settings,metrics,accounts}`, `static/features/*`). Inside each feature it's organized by technical step at file granularity, a leftover of the 150-line split. The dialer is the clearest case: 11 Python files plus 20 JS files, sliced by verb (queue, slots, timing, calls, outcomes) rather than by the state they own. Mean scatter is about **2.7×**.

---

## 5. Findings by category

### 5.1 Organization

**O1. The dialer state machine has no owner. High.**
- **Evidence:** `last_event` is written in 7 files, and `active`, `in_flight` and `pending_outcome` in 5 each. Measured by script: 16 attributes are written in 3 or more files, out of 53 attributes touched. Transitions into wrap-up live in `call_events.py:104-114,128-140`, `ended.py:54-63` and `outcomes.py:34-35`; out of wrap-up in `outcomes.py:34-39` and `queue.py:168-178`; pause in `queue.py:145`, `calls.py:78` and `ended.py:78-80`. VERIFIED.
- **Why it matters:** every call-flow change means reasoning about five writers and two kinds of threads (webhooks and timers). The `hangup_active`/`skip_active` near-copy (0.70 token similarity, `call_events.py:93-147`) shows the result.
- **Fix:** a `DialerSession` with named transition methods (`on_pickup`, `on_hangup`, `on_outcome`, `pause`, ...). Each one mutates under the lock and returns the side effects (Twilio hangups, metric bumps, saves) to run after the lock is released. This also fixes C7.
- **Effort:** L.

**O2. Ownership is misplaced across features. Medium.**
- **Evidence:**
  - The prospect status route is in `features/dialer.py:164-170,185`.
  - The dialer's summary dialog is bound by `_prospects/transcript.js:44`.
  - Arcade preference inputs are bound in `main.js:27-35`.
  - Dialer code opens the settings UI (`_dialer/session.js:7,29`, `lead.js:7,50`).
  - `settings.persist`/`reload` live in `accounts.py:95-118`.
  - VERIFIED.
- **Fix:** move each to its owner.
- **Effort:** S.

**O3. File and folder names don't match their contents. Medium.**
- **Evidence:**
  - `css/06-dialogs.css` defines `main`, `.metrics-panel` and `.dialer-run-panel` (`06-dialogs.css:55,68,72,74`).
  - `csv_import.py` holds the manual-lead factory (`csv_import.py:228-295`).
  - `session_stats.py` holds stage, local time and calling hours.
  - `call_events.py` sits beside `_call_events/`.
  - `crm_store/` contains one dead file.
  - "connected" means a dialer *stage* (`session_stats.py:18`), a *metric* that includes voicemail (`ended.py:37`), and a JS state, while the session uses "connects" for the same idea as the metric.
  - VERIFIED.
- **Effort:** S–M (renames happen with the moves in §8).

### 5.2 Granularity

**Merge candidates.** Each list changes together and fails AGENTS.md's own test: "can I change A without opening B?"

| Merge | Today | Merged size | Why it's cohesive |
|---|---|---|---|
| `_dialer/session.js` + `lead.js` + `connect.js` | 33 + 56 + 68 | ~110 after de-duplication | Same start→connect→cleanup flow. The cleanup block is copied 3 times (0.84 / 0.96 token similarity). |
| `_dialer/outcomes.js` + `outcome-row.js` + `keyboard.js` (outcome part) | 73 + 23 + 35 | ~120 | One button id list, duplicated in `keyboard.js:15`, `outcome-row.js:8-11` and `outcomes.js:69-72` |
| `_dialer/stage.js` + `timer.js` + `effects.js` | 128 + 22 + 9 | ~150 | The timer exists only for the stage, and `effects.js` is a 9-line mutable hook object |
| `_dialer/controls.js` + `queue.js` + `render-dialer.js` | 30 + 27 + 45 | ~100 | One render pass over one state slice |
| `_dialer/pool.js` + `pool-view.js` | 13 + 65 | ~78 | Controller and view of one panel |
| `_dialer/summary.js` + `session-goal.js` | 45 + 65 | ~110 | Both are session-stats UI |
| `_prospects/table.js` + `rows.js` + `query.js` + `selection.js` | 66 + 109 + 41 + 2 | ~215 | `selection.js` is 2 lines of shared state for these three files |
| `static/features/arcade.js` + `_arcade/*` (5 files) | 46 + 437 | ~430, or keep the parts and drop the 23-forwarder class | The class is pure indirection (`arcade.js:17-41`) |
| `features/_dialer/slots.py` + `timing.py` | 54 + 43 | ~95 | Both are timers that call `fill_slots`. The split only existed to dodge a size rule (`ARCHITECTURE_MAP.md:73-79`). |
| `features/_dialer/call_events.py` + `_call_events/*` | 147 + 238 | ~385 | One dispatcher with three handlers. A folder for 3 files breaks AGENTS.md:5. |
| `shared/infra.py` + `shared/_infra/*` | 13 + 235 | `shared/supabase.py` (~180) and `shared/files.py` (~50) | Removes a barrel and a 2-file folder |
| `tests/test_dialer_session/part_1..4` + `__init__` | 309 | one file, ~310 | Mixin test classes break AGENTS.md:6 |
| `tests/test_transcript_storage/*` | 246 | `test_prospects.py` | Same reason |
| 14 CSS files | 1,731 | ~6 feature files, each selector defined once | 140 selectors are defined in 2–7 files, and the numbered files are about 120 lines of cut-up rules |

**Split candidates** (more than one reason to change):

- **`features/_dialer/projection.py`.** The live call view and the prospect list view change for different reasons and at different rates. Split the poll payload (call state only) from the leads payload (already versioned by `leads_version`). This also removes `read_env` from every poll (`projection.py:65`).
- **`features/settings.py`.** Validation, view shape, `.env` persistence and Supabase persistence (`settings.py:7-37 / 44-67 / 70-103 / 106-141`). Split into schema plus service plus two repositories.
- **`features/_prospects/csv_import.py`.** CSV heuristics vs the lead model (phone and timezone normalization, limits, manual factory). Move the lead model into its own module.
- **`features/_dialer/session_stats.py`.** Pure session rules (keep) vs metric I/O wrappers (`session_stats.py:127-133`), which belong to the session service.

### 5.3 Dependency structure

**Intended layers**, from AGENTS.md:9 and refined: browser UI → HTTP routes → dialer application logic → domain rules → storage and adapters → shared.

**Edges that point the wrong way (VERIFIED):**

| Edge | Evidence | Problem |
|---|---|---|
| Twilio adapter → settings feature | `features/_dialer/twilio_api.py:3` (`from features.settings import values`), used at `:81,108` | The adapter reads configuration itself instead of receiving credentials |
| Projection (view) → `.env` disk I/O | `projection.py:5-6,65` | The view layer does config I/O on every poll |
| Feature routes → `web.py` callbacks | `features/settings.py:145,150`, `prospects.py:130,136` call `request.ctx.*`, defined in `web.py:225-244` | Features depend on an untyped object supplied by the HTTP layer, which calls back into `Dialer` and the runtime |
| Domain rule inside storage adapters | callback expiry is in `backend_local.py:94-111` and `backend_supabase.py:54-67` | The rule has two copies (0.84 similarity) living in persistence |
| Dialer → metrics I/O under the lock | C7 | Application logic does I/O inside a critical section |
| JS: dialer → settings UI | `_dialer/session.js:7`, `lead.js:7` | Cross-feature UI dependency |
| JS: prospects → dialer | `_prospects/menu.js:3`, `_prospects/transcript.js:4` | The second one exists only to bind the dialer's dialog |
| JS: auth → dialer, settings | `auth.js:2-3` | Acceptable for a boot module, but undeclared |
| JS core mutates core at import | `_core/api.js:10` (`showToast.report = …`) | Hidden wiring between core modules |

There are no cycles, and lower Python packages never import `web` or `server` (VERIFIED by the graph). Importing a storage module doesn't pull in the dialer or Twilio (`features.prospects` loads 13 app modules and no Twilio). Importing `features._dialer.twilio_api` pulls in Twilio. **Strength: keep it.**

**Third-party isolation:**

- **Twilio REST:** isolated in `twilio_api.py`. Good.
- **TwiML:** two styles. Hand-written XML strings (`call_events.py:18,51-57,69,77,86-90`) and the SDK `VoiceResponse` (`transcript.py:11-23`).
- **Twilio callback parameter names** are parsed in 6 files (count of `CallSid|CallStatus|AnsweredBy|…` per file: `calls.py` 8, `transcript.py` 4, `call_events.py` 4, `hooks.py` 3, `pickup.py` 2, `ended.py` 1).
- **PostgREST syntax** (`eq.`, `on_conflict`, `merge-duplicates`, `PGRST205`) appears in 5 files outside the client (`backend_supabase.py` 9, `metrics.py` 8, `settings.py` 4, `migrate_to_supabase.py` 4, `accounts.py` 1). The "table missing" string match is duplicated (`accounts.py:104-105`, `settings.py:115`).
- **Browser SDKs:** isolated. Twilio Voice is only in `_voice/connect.js` and `connect.js`; supabase-js only in `auth.js`. Good.

**Contracts:**

- **Implicit everywhere.** The prospect backend interface is 13 members (`leads`, `lock`, `revision`, `snapshot`, `timezone_groups`, `csv_bytes`, `add_lead`, `add_csv`, `remove`, `save`, `leads_locked`, `expire_locked`, `save_locked`) with no `Protocol`. The backends match by name only.
  - `LocalBackend.save` exists for tests and the migration script, while `SupabaseBackend` has no `save` at all. `ProspectStore.save()` (`prospects.py:55-56`) raises `AttributeError` on Supabase. That's VERIFIED by reading; nothing calls it in production.
  - The metrics stores differ in contract. Supabase validates keys and amounts (`metrics.py:99-104`); local accepts anything (`metrics.py:44-49`). The dialer checks capability with `hasattr` (`session_stats.py:128`, `queue.py:204`).
- **No lead type.** The lead dict is constructed in `csv_import.py:205-217` and `:245-257` (and in dead `crm_store/leads/manual.py:43-55`). `call_log` is added later (`prospects.py:120`).
- **Write-only fields.** `review_count`, `call_log` and `created_at` are never read by the UI (0 JS references) or the exporter (VERIFIED).

**Hidden coupling inventory:**

| Mechanism | Connects | Evidence |
|---|---|---|
| Handler-identity dispatch | route table → body parsing | `web.py:187-190` |
| Hard-coded routes beside the route table | `/api/auth/config`, `/api/health`, `/api/debug`, DELETE | `web.py:125-130,168-170,219-220` duplicate `SYSTEM_ROUTES` at `web.py:61-66` |
| Error "profiles" as strings | route → error mapping | `web.py:150-163`. Handlers also catch the same errors themselves (`dialer.py:110-128`, `metrics.py:211-214`). |
| `FeatureContext` | features → dialer and runtime | `web.py:225-244` |
| `HandlerMixin` | request object ↔ response helpers | `_web/respond.py:21`, `web.py:105`, `hooks.py:13` (breaks AGENTS.md:6) |
| `getattr`/`hasattr` on our own objects | web/accounts/dialer → Dialer and metrics | `web.py:32-33,117`, `dialer.py:91-92,97`, `accounts.py:98,113`, `projection.py:62`, `queue.py:204`, `session_stats.py:128` |
| String-keyed webhook actions | `_url(state, call, "answer"/"status"/"machine"/"transcript"/"agent-ended")` → `call_events.py` if-chain | `calls.py:34-48`, `call_events.py:26-70` |
| TokenIndex registry | Twilio callbacks → tenant `Dialer` | `twilio_api.py:61-78`, `hooks.py:27-34` |
| JS registries (5) | core ↔ features | `registerRenderer`, `registerTable`, `registerCallerPool` (`_core/registry.js`), `registerTranscriptActions` (`_core/transcript.js:41`), `registerAudioDevices` (`core.js:40`), plus mutable `stageEffects` (`effects.js`, wired at `dialer.js:14-25`) and `setStartNewSession` (`summary.js:5`) |
| DOM events | rows → records | `"prospect-status"` CustomEvent (`rows.js:89`, `records.js:9`) |
| Shared mutable `state` | 11 JS files call `Object.assign(state, …)` | Measured |
| One key, two shapes | `state.settings` is written by `applySavedSettings` (secret-bearing `settings_state` shape, `settings.js:7`) and overwritten every poll with the projection shape (`projection.py:66-76`) | VERIFIED |
| Golden page snapshot | any markup change → `docs/page-before.html` | `tests/test_http.py:97-125` |
| Partial order duplicated | page assembly ↔ static checker | `_web/respond.py:59-66` vs `scripts/check_static.py:10-17` |

**Side effects at import time:**

- `_core/format.js:1` parses `#vocabulary` from the DOM when the module loads.
- `performance.js:34`, `prospects.js:5-7`, `dialer.js:14-32` and `_voice/connect.js:9` register themselves at import, so `main.js:5` imports `performance.js` *only* for that side effect.
- Python has no harmful import-time effects. VERIFIED.

### 5.4 Domain rules, state, sources of truth

| Rule | Where it's defined or decided | Authoritative | Diverged? |
|---|---|---|---|
| Statuses | `shared/vocabulary.py:5-13`; literal tuple `outcomes.py:19` and again `:46-48`; `prospects.html:10-16` options; 46 status literals in `features/` and `static/` | vocabulary | The HTML option list is **not** tested, despite `ARCHITECTURE_MAP.md:45-48` claiming it is (`test_vocabulary.py` only checks metric keys). Not diverged yet. VERIFIED |
| Dispositions | `vocabulary.py:15-21`; JS hard-codes `"booked"`, `"not_interested"`, `"no_answer"`, `"do_not_call"`, `"callback"` (`outcomes.js:64-72`); the button id order is duplicated (`keyboard.js:15`) | vocabulary for mapping; JS for the set | `interested` is a valid outcome status (`outcomes.py:19`) but no disposition produces it, so the `interested` metric is reachable only from the table dropdown. VERIFIED |
| What counts as a connect | session: any pickup, including voicemail (`pickup.py:20-22`); metric `connected`: bumped at end if picked up, including voicemail (`ended.py:23,37`) | Two places, counted at different moments | A call that never gets an end webhook (for example after a restart) counts in the session but not the metric. INFERRED |
| What counts as a conversation | `ended.py:40-42` (excludes AMD voicemail) + `session_stats.record_conversation:65-74` (threshold) + threshold default `vocabulary.py:69` + validation `settings.py:17` | `ended.py` | `answered_by` of `"unknown"`, or AMD arriving after hangup (it is ignored after `end_processed`, `pickup.py:43`), counts as a conversation. INFERRED. Confirm with a call where voicemail AMD arrives late. |
| Callback scheduling | +24 h default in `prospects.py:79`, `csv_import.py:244` and dead `manual.py:51`; browser "next business day 9:00" in `_core/time.js:12-24` (doesn't skip weekends); `no_answer` maps to `call` (`vocabulary.py:19`); expiry in `backend_local.py:94-111` and `backend_supabase.py:54-67` | No single owner | The two expiry copies are logically equal (0.84). When a callback expires it becomes plain `new`, losing the fact that it was a callback, and `random.sample` gives it no priority (`slots.py:25`). VERIFIED |
| Calling hours / timezones | `vocabulary.py:45-65`; inline copy `stage.js:82-89` (0.86 similarity to vocabulary); keyword list `csv_import.py:59-60`; `session_stats.local_time`; `_core/time.js:26-28` | vocabulary | Enforcement deleted (C1). `_timezone` returns the raw text for unknown zones (`csv_import.py:75`), so arbitrary strings become pool groups. VERIFIED |
| Phone normalization and dedupe | `csv_import._phone:24-49` (lead phones), `twilio_api.normalize_phone:44-53` (caller ids; 0.67 similarity, no `00`/extension/scientific handling), `_core/phone.js` (display). Dedupe: `parse_csv:184-197`, `build_manual_lead:236` | `_phone` | Divergent dead copy in `crm_store/leads/manual.py`. Supabase dedupe only checks this process's cache. VERIFIED |
| Metric "today" | UTC date (`metrics.py:42,106`) | — | In America/New_York, "today" rolls over at 8 pm EDT. VERIFIED |

**Data shapes:**

- **Lead:** see §5.3. No schema.
- **Call record:** a dict documented in a docstring (`state.py:3-8`). Keys are added ad hoc later: `connected_at`, `machine_counted`, `outcome_chosen`, `wrapping`.
- **State payload:** 29 keys, locked by `tests/test_http.py:11-40`. That's good, and it's the only real contract in the system.
- **Unused payload fields:** `manual_lead_id` is produced but has 0 JS reads. The vocabulary JSON ships 10 keys, and 7 of them are never read by JS (`dispositions`, `outcomeMetric`, `defaultOutcomeMetric`, `metricKeys`, `stages`, `callStates`, `settingKeys`).

**State ownership:**

| State | Stored | Mutated by | Survives restart | Copies |
|---|---|---|---|---|
| Call / dialer | `DialerState` in memory | 5 or more files (O1) | No. Live Twilio calls whose tokens are lost get `<Hangup/>` (`call_events.py:17-18`), or 404 when signed in. | `state` in the browser, overwritten every 1.5 s |
| Leads | `crm_data/part-*.json` or Supabase `prospects` | `ProspectStore` + backends | Yes | Supabase backend caches per process **forever** (`backend_supabase.py:38-41`) and never refetches. Browser `state.leads`. |
| Session stats | `state.session` + saved on every change | dialer parts | Saved, not resumed | `session_stats` in the payload |
| Settings | `.env` (local) or `dialer_settings` + `.env` merge | `settings.py`, `accounts.py`, `Dialer.save_settings` | Yes | `account_values` (memory), `state.settings` (snapshot at `start`, `queue.py:48`), re-parsed every poll (`projection.py:65`), browser `state.settings` (two shapes), **plus** arcade sound and volume in `localStorage` that gate the same sounds (`_arcade/audio.js:13-14,40`, `_arcade/shell.js:41,77`) |
| Metrics | `metrics.json` or 3 Supabase tables | `_bump` callers | Yes | Supabase snapshot cached 10 s (`metrics.py:149-154`) |

**Concurrency:**

- C3: lost updates. C7: I/O under the lock. C2: write-after-mutate. C12: multi-file write.
- `fill_slots` takes `crm.snapshot()` outside the lock and then decides inside it (`slots.py:10-29`). A lead marked DNC in between can still be dialed. INFERRED (narrow window).
- `write_env` does an unlocked read-modify-write of `.env` (`config.py:49-65`), so two concurrent saves race. INFERRED.
- `.env` comments are dropped on every save. VERIFIED by probe.
- Lock ordering: dialer → metrics/crm only, never the reverse, so no deadlock was found. VERIFIED by reading.

### 5.5 Duplication and drift (token-level `difflib` ratios, `autojunk=False`)

| Copies | Ratio | Diverged? |
|---|---|---|
| `timezone_groups` local vs Supabase (`backend_local.py:118-125` / `backend_supabase.py:75-82`) | 0.95 | No |
| `connect.js:54-63` vs `session.js:20-28` cleanup | 0.96 | No |
| `settings_state` prefs vs projection settings (`settings.py:58-66` / `projection.py:67-75`) | 0.93 | No, but 5 hand mappings of the same 9 keys: also `save_settings:71-82`, `settings.js:14-23` and `:83-91` |
| Metrics daily series local vs Supabase (`metrics.py:71-82` / `197-207`) | 0.86 | No |
| `stage.js:82-89` zones vs `vocabulary.py:45-52` | 0.86 | No (a drift risk) |
| `expire_due` vs `_expire` | 0.84 | Behavior equal; I/O differs (one save vs N PATCHes) |
| `session.js` vs `lead.js` error cleanup | 0.84 | Yes: `lead.js` only cleans up if a session started |
| `hangup_active` vs `skip_active` | 0.70 | Yes, intentionally |
| `normalize_phone` vs `_phone` tail | 0.67 | **Yes** |
| `add_lead` / `add_csv` local vs Supabase | 0.57 / 0.51 | **Yes**: total bug (C10) |
| `build_manual_lead` live vs `crm_store` copy | 0.46 | **Yes**: speaker `Agent` vs `Prospect`, `review_count` source, length limits, error text |
| Atomic temp-and-replace write | 4 copies: `metrics.py:33-38`, `backend_local.py:52-54` and `:88-91`, `config.py:62-65` | The shared `write_json_atomic` (`files.py:50-54`) is exported and **never used**. `dumps_json` (`files.py:57`) is unused too. |
| "Sign in with Google to continue." | 6 occurrences in 3 files | — |
| API paths in JS | 33 string sites in 16 files; `/api/state` in 6, `/api/stop` in 4 | — |
| "Standard columns" for CSV | `csv_export.py:8-10` (6 names) vs `query.js:6` (regex, about 20 names) vs import heuristics | **Yes**: export shows columns the table hides, and the round trip loses `timezone`, status and `call_log` |

### 5.6 Cross-cutting

- **Configuration and secrets.** C4, C5, C6 and C13. `.env` is correctly gitignored and has mode 600 after writes (`config.py:66-69`). The Supabase service key never reaches the browser; only `url` and `anonKey` do (`web.py:15-22`). VERIFIED. The Twilio Voice identity is fixed at `"prospect_desk_agent"` for every tenant (`twilio_api.py:120`). That's harmless on separate Twilio accounts and ambiguous on a shared one. INFERRED.
- **Error handling.** Three styles:
  - String profiles in `web.py`
  - Per-handler try/except that duplicates them (`dialer.py:110-128`, `metrics.py:211-214`, `prospects.py:144-163`)
  - Catch-all 502 for programming errors (`web.py:203-208`)
  
  GET routes with profile `"none"` have no handler-level guard. When `get_settings` → `load_app_settings` raises `OSError` (Supabase down), the exception escapes `do_GET` (`web.py:163`) and the client gets a dropped connection, not JSON. VERIFIED by reading the code path; not exercised.
- **Logging and observability.** One debug log, truncated on every start, with no rotation, printed to stdout as well (`files.py:21-42`). `record_activity` mirrors to it (`state.py:65-66`). The in-UI activity log is capped at 40 entries (`state.py:64`). There are no request ids and no metrics on webhook latency, although `hooks.py:68-74` logs elapsed ms. That's a good start.
- **Security and tenants.**
  - Signature validation on every hook (`hooks.py:49-56`, constant-time compare in `twilio_api.py:94`).
  - Static path traversal is guarded (`respond.py:129-135`).
  - Supabase tenant scoping by `user_id` filters on every query (`backend_supabase.py:18-22`, `metrics.py:92-96`). `_scope` silently drops the filter when `user_id` is falsy. That's unreachable in signed-in mode today, but fragile.
  - RLS is on, with no policies and all grants revoked (`schema.sql:59-78`). Correct for service-role-only access, but setup.md:10 promises "Google-account policies" that don't exist.
  - `dialer_sessions.id` is a timestamp (`session_stats.py:32-34`), upserted on `id` alone across tenants (`metrics.py:124-136`). The collision chance is negligible, but the key is wrong.
- **Testability.**
  - **Good:** pure functions in `session_stats.py`, injected `crm` and `metrics`, threads and timers are patchable (`test_call_flow.py:15-40`), fast in-process servers (`tests/local_server.py`).
  - **Bad:** suite red; mixin test parts; a fixture in `Claude outputs/`; a test that writes into `docs/`; private facade methods kept alive only for tests; no backend contract test; no test for calling hours (the existing test asserts the *pure* function, so it kept passing after enforcement was deleted).
- **Dead code and endpoints** (searched py/js/html/css/tests/strings):
  - `crm_store/leads/manual.py`, `static/js/controllers/new-prospect.js`, `tests/test_manual_prospect.py` (broken)
  - `scripts/check_js_urls.py`
  - `dumps_json`, `write_json_atomic`
  - `within_calling_window` and `local_time` in production
  - 7 `Dialer` methods used only by tests (`_new_call`, `_pickup`, `_machine_result`, `_transcription_event`, `_call_ended`, `fill_slots`, `choose_outcome`)
  - `GET /api/auth/me`: no JS caller, only `test_http.py`
  - `QUIET_HTTP` entries for nonexistent `/app.css` and `/app.js` (`config.py:21`)
  - `call_log.csv`
  - 7 unused vocabulary keys
- **Docs drift.** See §3. Also `ARCHITECTURE_MAP.md:10` says "37 tests" (there are 44 functions), and `:45-48` claims a test that doesn't exist.
- **Build and tooling.** No `pyproject.toml`, no lint, no CI. `requirements.txt` is unpinned (`twilio`, `tzdata`). Frontend CDN versions are pinned (good). No `.gitattributes` (phantom CRLF diffs).

---

## 6. Phase 6 — change-impact simulation

The counts come from the traces above. "Read" includes "edit". They're estimates of what is *safe*, not of the minimum someone might get away with.

| Change | Must edit | Must also read | Read / edit | What forces the extra reads |
|---|---|---|---|---|
| 1. Change what counts as a "conversation" | `_call_events/ended.py:40-42`, maybe `session_stats.py:65-74` | `pickup.py` (where `answered_by` comes from, and late-AMD behavior), `calls.py` (call dict), `call_events.py` (how hangup routes), `settings.py` (threshold), `tests/test_dialer_session/part_2.py`. If it should appear in Performance: `vocabulary.METRIC_KEYS`, `schema.sql` (5 lists), `metrics.py`, `performance.js`. | 7 / 2 (13 / 6 with the dashboard) | The rule is split between end handling and session math; AMD timing lives in another file; no metric for it |
| 2. Add a prospect column (import, storage, export, both tables, manual add) | `csv_import.py` (parse, `build_manual_lead`, `_LIMITS`, and possibly `JUNK_HEADER`, e.g. `email` is treated as junk at `:20`), `csv_export.py`, `_prospects/query.js` (standard regex, search, signature), `rows.js`, `table.js` (headers), `pool-view.js` and `prospects.html` (pool thead), `add-prospect.js`, `docs/page-before.html` | `backend_local.py`, `backend_supabase.py` (no schema, so no change, but you must check), `prospects.py`, `stage.js` (shows fields), dead `crm_store/leads/manual.py` and `new-prospect.js` (to rule them out), `test_http.py` | 15 / 9 | No lead schema; three "standard column" lists; two tables built separately; golden HTML snapshot |
| 3. Add a call disposition | `vocabulary.py` (`DISPOSITION_TO_STATUS`, maybe `STATUSES`/`OUTCOME_METRIC`/`METRIC_KEYS`), `outcomes.py:19,46-48` (if new status), `dialer.html:48-52`, `outcomes.js`, `outcome-row.js`, `keyboard.js`, CSS outcome button rules, `prospects.html:10-16` (if new status), `schema.sql` (if new metric), `page-before.html` | `session_stats.py`, `projection.py`, `charts.js`, `test_vocabulary.py`, `test_http.py` | 15 / 8–11 | JS doesn't use the vocabulary's dispositions; button ids are listed in three places |
| 4. Handle a new Twilio webhook or AMD result | `calls.py:31-50` (subscribe), `call_events.py:26-70` (string dispatch), `pickup.py:33-66` (label parsing), maybe `vocabulary.METRIC_KEYS` + `schema.sql` + `session_stats` bump, `monitor.js` / `stage.js` labels, CSS `data-state` | `hooks.py` (path shape `len(parts)==3`), `twilio_api.py` (`_url`, signature), `state.py` (call keys), `ended.py` (`end_processed` interplay), `projection.py` (exposure), Twilio console | 11 / 4–7 | String-keyed actions; Twilio parameter names in 6 files; call dict implicit |
| 5. Add a dialer setting, from UI to persistence to behavior | `vocabulary.SETTING_DEFAULTS`, `settings.py` (`preferences` range table, `settings_state`, `save_settings` mapping: 3 places), `projection.py:66-76`, `settings.html`, `settings.js` (apply and submit), the behavior file (reading `state.settings`), `.env.example`, `test_http.py:45-60` `SETTINGS_KEYS`, `page-before.html` | `config.py` (`write_env` defaults), `accounts.py` (persist), `queue.py:47-48` (when `state.settings` refreshes: only at `start` and save) | 13 / 10 | The same 9 keys are hand-mapped 5 times, and settings are snapshotted at start |
| 6. Swap or add a storage backend | `prospects.py:15-19` (backend choice), new backend (13-member implicit interface), `metrics.py` (new store, `hasattr`-compatible), `settings.py` (`load_app_settings`/`save_app_settings` are Supabase-only), `accounts.py:32-93` (backend choice hard-coded), `config.py`/`vocabulary.py` (env keys), migration script | both existing backends, `_infra/supabase.py`, `session_stats.py`, `queue.py:204`, `tests/test_transcript_storage/fixtures.py` | 14 / 8 + new | No `Protocol`s; settings storage isn't behind a repository; backend choice is spread across three modules |

**Realistic average for a small change: about 12 files read, about 7 edited** (mean of the six rows, using the base case where a row gives two figures). That's an estimate derived from the traces.

**The top three structural causes:**

1. **Concepts are hand-mapped in several places** (settings ×5, statuses and dispositions in Python, HTML and JS, standard columns ×3, timezones ×4), with no schema to generate from.
2. **No owner for the call state machine or the lead model.** Rules are scattered across 5 dialer files, both storage backends and the CSV module.
3. **Too many small files and hidden wiring** from the size rule: facades, barrels, registries, mixins, string dispatch, plus a golden HTML snapshot that turns every markup change into a two-file change.

---

## 7. Scorecard

Anchors: 10 = a new senior engineer changes it by reading 1–3 obvious files; 5 = workable, but needs tracing across many files or hidden mechanisms; 1 = changes routinely break unrelated things.

| Dimension | Score | Justification |
|---|---|---|
| Feature organization | 5 | The top-level feature folders are real, but each feature is cut by verb into micro-files, and ownership leaks (the prospect status route sits in the dialer, the dialer's dialog is bound by prospects). |
| Cohesion | 4 | `projection.py`, `features/dialer.py` and `session_stats.py` each mix several reasons to change, while the dialer and arcade JS split single concerns across 3–6 files. |
| Coupling | 4 | 16 dialer attributes are written from 3 or more files, and there are 5 JS registries, 11 `Object.assign(state)` writers, `FeatureContext` callbacks and string-dispatched webhooks. |
| Dependency direction | 7 | Zero cycles in either language and clean storage imports; the wrong-way edges are few and named (twilio_api → settings, projection → `.env`, features → `ctx`). |
| Single source of truth | 4 | `vocabulary.py` is a good start, but 7 of its 10 browser keys are unused, settings are mapped 5 times, the calling-hours rule exists but isn't applied, and DNC can diverge between cache and store. |
| Duplication | 5 | Mostly small near-copies (0.84–0.96), but 4 of the copies have already diverged (phone normalization, manual-lead builder, `add_csv` total, CSV column sets). |
| Naming | 4 | `06-dialogs.css` holds layout, `csv_import` builds manual leads, "connected" means three things, and 16 ghost package directories still look like code. |
| Testability | 5 | The pure rules and injectable collaborators are testable and fast, but the suite is red, tests are mixins, there's no backend contract test, and a golden HTML snapshot blocks markup changes. |
| Agent/onboarding friendliness | 3 | No README, 835 lines of stale plan docs with 185 dead paths, phantom CRLF diffs, tracked `.pyc` files, and divergent dead copies of live functions. |

---

## 8. Target architecture and migration plan

### 8.1 Target module map (line counts are rough targets)

```
server.py                        ~60   composition root: build runtime, start both servers
http/
  app_server.py                  ~230  parse, CSRF/Origin check, route table (method, path, handler, body kind), one error mapper, static + page  ← web.py, _web/respond.py
  twilio_hooks.py                ~90   signature check, token→session routing                                                               ← _web/hooks.py
accounts.py                      ~110  tenant resolution, Account factory, health, startup config validation (fail fast on C9)            ← features/accounts.py (minus settings persistence)
dialer/
  routes.py                      ~80   /api/start … /api/live, /api/voice-token                                                              ← features/dialer.py route fns
  session.py                     ~400  DialerSession: state + named transitions; returns side effects, executed after the lock is released  ← state.py, queue.py, calls.py, slots.py, timing.py, outcomes.py, Dialer facade
  call_events.py                 ~300  interpret Twilio callbacks (status, answer, AMD, transcript, end) → session transitions               ← call_events.py, _call_events/*
  rules.py                       ~170  pure: stage, connect/conversation definitions, disposition→status/metric, calling window, session math ← session_stats.py
  twilio.py                      ~200  REST, all TwiML builders, access token, signature, Twilio param names                                 ← twilio_api.py + TwiML literals
  live_view.py                   ~90   call-only poll payload (no leads, no disk I/O)                                                        ← projection.py
prospects/
  model.py                       ~150  Lead TypedDict, phone/timezone normalization, limits, manual lead factory                              ← csv_import.py (part), normalize_phone
  csv_io.py                      ~280  import heuristics + export mapping, round-trip tested                                                  ← csv_import.py, csv_export.py
  service.py                     ~200  status/callback/expiry/dedupe/transcript/call log rules; write-then-cache                             ← prospects.py, both backends' rules
  store.py                       ~30   ProspectRepo Protocol
  store_local.py                 ~90   one atomic JSON file (reads legacy part-*.json once)                                                 ← backend_local.py
  store_supabase.py              ~120  PostgREST only                                                                                         ← backend_supabase.py
  routes.py                      ~70
metrics/
  service.py / store_local.py / store_supabase.py  ~220 total; Supabase increments via one SQL function (atomic)                               ← features/metrics.py
settings/
  schema.py                      ~90   ONE table: key, default, type, range, UI field, secret, scope → validation, view, persistence keys, browser JSON
  service.py                     ~110  merge, validate, save; secrets write-only ("has_*" flags only)
  store_env.py / store_supabase.py ~100                                                                                                      ← settings.py, accounts.py, config.write_env
  routes.py                      ~40
shared/  vocabulary.py ~110, supabase_client.py ~180, files.py ~60 (atomic write, debug log), config.py ~50
static/
  core/      api.js (incl. API path constants), state.js, format.js, time.js, notify.js, nav.js, transcript.js   (no barrel; one renderer registry)
  dialer/    dialer.js (entry + bind), call-session.js, stage.js, controls.js, disposition.js, monitor.js, session.js (goal + summary), pool.js, voice.js, voice-devices.js, voice-test.js, dialer.html, dialer.css
  prospects/ prospects.js, table.js, add-prospect.js, csv.js, transcript.js, prospects.html, prospects.css
  performance/ performance.js, charts.js, performance.html, performance.css
  settings/  settings.js, settings.html, settings.css
  arcade/    arcade.js (functions over one state object), arcade.css
  auth/      auth.js
  shell/     shell.html, shell-end.html, tokens.css, shell.css
tests/  test_dialer_rules.py, test_dialer_session.py, test_call_events.py, test_prospects.py (runs against both stores), test_csv_io.py,
        test_settings.py, test_metrics.py, test_http.py, test_static.py, test_architecture.py, fixtures/example_leads.csv
```

**Where each current file goes:** shown by the arrows above. Not listed: `dialer.py` (launcher; keep or fold into `server.py`), `scripts/migrate_to_supabase.py` (keep; add `--user-id`), `scripts/check_static.py` (keep; read the partial list from one place). To delete: `crm_store/`, `static/js/`, `scripts/check_js_urls.py`, `shared/infra.py`, `shared/_infra/`, `static/core.js`, `tests/test_manual_prospect.py`, the ghost directories, `call_log.csv`, `docs/ARCHITECTURE_MAP.md`, `docs/FRONTEND_MAP.md` (replace with a one-page README).

### 8.2 Dependency rules to enforce (with a `test_architecture.py` over the import graph)

1. `http` → `<feature>/routes` → `<feature>/service|session` → `rules|model|schema` → `store_*` / `twilio` → `shared`. Never upward. A feature imports another feature only through its `service`.
2. `rules.py`, `model.py` and `schema.py` import only the stdlib and `shared/vocabulary`. No I/O, no clock reads (take `now=`).
3. Only `dialer/twilio.py` imports `twilio` or builds TwiML. Only `store_supabase.py` files and `shared/supabase_client.py` use PostgREST syntax.
4. No network or disk I/O while holding a session lock. Enforce it with a test: a slow fake store must not block `live_view` for more than 50 ms.
5. Every store implements its `Protocol`, and one contract test runs against both implementations.
6. Frontend: feature modules import `core/*` and their own folder only. Cross-feature calls go through two or three named core hooks listed in `core/registry.js`. No barrels, and no status, disposition, setting or timezone literals in JS (a static test greps for them).

### 8.3 Migration order (the app works after every step)

| Step | What | Risk / what could break | How to verify | Size |
|---|---|---|---|---|
| 0 | **Green and clean.** Delete `crm_store/leads/manual.py`, `static/js/controllers/new-prospect.js` and `tests/test_manual_prospect.py` (or port its 4 assertions to `features._prospects.csv_import`). `git rm --cached` `__pycache__` and `call_log.csv`; remove the 16 ghost directories; add `.gitattributes` (`* text=auto eol=lf`); move `example_leads.csv` to `tests/fixtures/`; delete `check_js_urls.py`, `dumps_json` and `write_json_atomic` (or use it); stop `test_http` writing into `docs/`. | Low. The only risk is that the `max-pc` commit was intended work (Q7). | Suite at 39/39, then 41/41; `python -c "import server"` | S |
| 1 | **Safety-net fixes, each with a failing test first:** C4 (secrets write-only), C5 (reject non-JSON Content-Type plus Origin/Host allowlist), C2 (write, then update cache), C3 (an `increment_metric` SQL function, one RPC), C7 (collect side effects under the lock, run them after), C11 (persist once), C6 (signed-in users don't read Twilio keys from `.env`), C9 (fail fast at startup), C10, C14 (`--user-id`), C13 (fix the regex), and the Q1 decision on calling hours. | Medium. Settings UI behavior changes (secret fields become "leave blank to keep"); the SQL migration must be applied before deploy. | New unit tests; manual call on a test Twilio number; Supabase upgrade on staging | M |
| 2 | **Contracts.** A `ProspectRepo` and `MetricsStore` `Protocol`, a lead `TypedDict`, and one contract test parameterized over local and Supabase-fake. Remove the `hasattr`/`getattr` checks. | Low | Contract test passes for both | S–M |
| 3 | **Settings schema.** One table generates `preferences()`, the view, the save mapping, projection settings and the browser fields. | Medium. The payload key set is locked by `test_http.py:45-60`. | `test_http` key sets unchanged; settings round-trip tests | M |
| 4 | **Dialer session.** Fold the `Dialer` facade, `queue`, `calls`, `slots`, `timing` and `outcomes` into `session.py` with named transitions. Merge `call_events.py` and `_call_events/*`. Move TwiML to `twilio.py`. Rewrite the 7 test-only private calls to use public transitions. | **High.** Call flow, timers, wrap-up. | `test_call_flow`, the dialer session tests, plus a new transition-table test (state × event → state); one live call each of human, voicemail, no-answer, hangup-while-ringing and skip | L |
| 5 | **Split the poll.** `/api/live` carries call state only, with no `read_env`; leads only through versioned `/api/state`. | Medium. The browser merge logic is in `poller.js:34-51`. | `LIVE_KEYS` test; profile that a poll does no disk I/O | M |
| 6 | **Prospects.** `model.py`, `service.py` (one expiry rule), `csv_io.py` with a round-trip test, and one atomic JSON file (read the old `part-*.json` once, then write `prospects.json`). | Medium. Local data migration. | Back up `crm_data/` first; round-trip test; manual import of `example_leads.csv` | M |
| 7 | **Frontend.** Delete the `core.js` barrel; merge the dialer and prospect micro-files (§5.2); one registry; summary binding moves to the dialer; JS reads dispositions, timezones and statuses from the vocabulary. | Medium. Wiring order (the `main.js` boot order). | `check_static.py`; click through every tab and dialog | M |
| 8 | **CSS consolidation** per feature, each selector defined once. | **Medium–high, visually.** Cascade order. | Playwright screenshots at 1440×900 and 390×844 before and after (planned but never run in the earlier refactor) | M–L |
| 9 | **Docs.** A one-page README: run, `.env`, Twilio console (TwiML App Voice URL = `{PUBLIC_BASE_URL}/hooks/voice`, tunnel to `:8765`), Supabase setup; plus `test_architecture.py` enforcing §8.2. Delete both plan docs. | Low | — | S |

**Leave alone:**

- `SupabaseClient` and its connection pool
- Twilio signature validation and the `TokenIndex` routing
- `serve_static`'s traversal guard
- The CSV header heuristics (move them, don't rewrite them)
- `test_http.py`'s payload-key contract (keep it; drop only the golden page snapshot or reduce it to an id inventory)
- DOM construction with `textContent`
- The no-cycles property

**What this plan does not fix:**

- Live call state is still in memory in a single process, so a restart drops the session. Fixing that needs persisted session state and resumable Twilio calls.
- Polling (1.5 s) instead of push.
- Thread-per-call.
- No horizontal scaling: the per-process Supabase cache assumes one server.
- Twilio console and tunnel setup stay manual.
- Local mode still has no user authentication beyond the CSRF guard.
- Transcripts still grow inside each lead's JSON blob.

---

## 9. Open questions (decisions that need you)

1. **Calling hours.** Enforcement was removed on purpose in `70366cb`, and setup.md now says calls aren't blocked. Yet Settings still asks for calling hours and the server validates them. Should the dialer enforce them (and what happens to `Unknown`-timezone leads: skip or allow?), or should the setting be removed? Given TCPA-style calling-hour rules, I'd recommend enforcing them with an explicit "allow unknown timezone" switch.
2. Should the **"Connected" metric** (Performance tab) include voicemail pickups? It does today (`ended.py:23,37`).
3. Should an **unknown or late AMD result** count as a conversation? Today it does if the call is 30 s or longer.
4. Hanging up a **ringing, unanswered** call forces a disposition (`call_events.py:108-114`). Is that intended?
5. **"No answer" → Callback (+24 h)** and metric `call_later` (`vocabulary.py:19,24`). Is that intended, or should no-answer go back to `new`?
6. Metrics **"today" is the UTC day**. Should it be your local day?
7. The **last commit `4607dfa` (`max-pc`)** re-added a "New prospect" dialog and a manual-lead builder against the deleted architecture, plus a test. Was that a feature you want ported (it differs: speaker `Prospect`, `review_count` from fields), or an accidental merge from a stale checkout?
8. Should signed-in users ever fall back to the server's `.env` Twilio credentials (a single-owner deployment), or never (true multi-tenant)? Today they do (C6).
9. Is **local mode** meant to be single-user only? If so, the CSRF guard is enough. If not, it needs auth.
10. Should the **next-business-day callback** skip weekends (`_core/time.js:12-24`)?
11. Should expired callbacks get **dial priority** over fresh `new` leads? Today they're indistinguishable (`backend_*` expiry and `slots.py:25` random sampling).

---

## Appendix: scripts used (run on copies in `~/audit` and `~/run`, never in the repo)

**Inventory (`metrics.py`).** Walks the tree, skipping `.git`, `.venv`, `__pycache__`, `node_modules` and `Claude outputs`. Counts files and lines per extension; computes median, under-20, over-150 and over-300 per language; lists folders, depth and files per folder.

**Import graphs (`graph.py`).** Python edges come from `ast` (`Import`/`ImportFrom` resolved to repo modules, with function-level imports recorded separately). JS edges come from a regex over `import … from` / `export … from` / bare `import "x"`, resolved relative to the importing file. It computes fan-in and fan-out, Tarjan SCCs for cycles, orphans, and missing targets.

**CSS duplication (`css.py`).** Strips comments, splits every `selector {` on commas, normalizes whitespace, and maps each selector to the set of files that define it.

**Similarity.** `difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False).ratio()` over `[A-Za-z_]+|\d+|\S` tokens of the cited line ranges.

**State writers.** A regex for `(state|self|dialer).<attr> = | += | .clear( | .append( | .pop( | .update( | .setdefault(` over `features/_dialer/**`, `features/dialer.py`, `accounts.py`, `web.py` and `_web/hooks.py`. JS used `Object.assign(state,` and `S.<field> =`.

**Forwarders.** `ast`: methods whose body is a single `return <call>`. Arcade used a regex for `name(args) { [return] fn(this, …); }`.

**Runtime probes (`probe.py`, `csrf.py`)**, run with a Python 3.10 venv with `twilio` 9.11.2 and `tzdata` installed in the VM home:

- P1 `fill_slots` outside the calling window
- P2 a signed-in `Dialer` reading a shared `.env`
- P3 `write_env` dropping comments
- P4 `add_csv` totals on fake-Supabase vs local
- P5 `resolve_account` with Supabase configured and no anon key
- P6 5 threads calling `SupabaseMetricsStore.bump` against a client with 50 ms GET latency
- P7 `public_state` latency while `fill_slots` runs with a 1 s fake metrics store
- P8 counting `dialer_settings` upserts per `FeatureContext.save_posted_settings`
- A fake Supabase that fails PATCH, to check cache divergence
- `csrf.py`: started `tests.local_server.LocalServers` in a temporary directory and POSTed `text/plain` JSON with a foreign `Origin`

**Tests.** `python -m unittest discover -s tests -t .` in `~/run`, with `Claude outputs/example_leads.csv` copied in because a test requires it.

**Git.** `git log -S'within_calling_window('`, `git show 70366cb`, `git log -S'PART_LINE_LIMIT'`, `git show 09e1122` (the 150-line enforcement), `git ls-files --eol`, `git log --format='%h %an %ad %s'`.
