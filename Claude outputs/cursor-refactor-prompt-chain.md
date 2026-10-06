# powerDialer: sequential Cursor prompt chain (feature-slice refactor)

Twenty-one prompts, run one at a time, each in a **fresh Cursor chat** with **Grok 4.7**.
Every prompt is one commit on one branch. If a prompt reports a failed check or a STOP, do not run the next one. Fix it or roll back that commit first (`git reset --hard HEAD~1`).

## How to run each prompt

1. Do the "Before" step listed for the prompt, if any.
2. Open a new Cursor chat in Agent mode. Pick Grok 4.7 at the effort level shown: **high** by default, **xhigh** where marked.
3. Paste the prompt block. Prompts marked **two-phase** stop after writing a plan. Read the plan, then reply `go`.
4. When it finishes, read its report table. Every row must say PASS.
5. Do the "You check" step: a 1–3 minute manual smoke test in the browser.
6. Run the next prompt.

Before P0, commit or stash your own work-in-progress (for example the `static/css/linear/metrics.css` change). P0 refuses to start on a dirty tree.

Note on line endings: the audit saw 161 files that differed only by CRLF. That may have been an artifact of how the audit read the repo, since your Windows git may convert line endings automatically. P0 checks for it and only normalizes if the noise is real.

## Chain at a glance

| # | Prompt | Type | Effort |
|---|---|---|---|
| P0 | Baseline, hygiene, standing rules | setup | high |
| P1 | Fix local store data loss | bug fix | high |
| P2 | Characterization safety net (HTTP, webhooks, static assets) | tests only | high |
| P3 | Security: stop sending secrets, block cross-site requests | bug fix | high |
| P4 | Small correctness fixes (callback crash, export, metrics RPC, etc.) | bug fix | high |
| P5 | Calling-hours decision (pick one variant) | behavior | high |
| P6 | Delete dead code | cleanup | high |
| P7 | `shared/` kernel (debug log, json file, env, time, Supabase client) | move | high |
| P8 | Single vocabulary (statuses, dispositions, metric keys, timezones) | consolidate | high |
| P9 | `features/metrics/` slice | move | high |
| P10 | `features/settings/` slice | move | xhigh |
| P11 | `features/prospects/` slice | move, two-phase | xhigh |
| P12 | Twilio adapter `features/dialer/twilio_api.py` | extract | high |
| P13 | Collapse the dialer into `features/dialer/` | move, two-phase | xhigh |
| P14 | Web layer and per-feature route tables | move, two-phase | xhigh |
| P15 | Frontend: `core/` and `features/dialer/` | move, two-phase | xhigh |
| P16 | Frontend: prospects, performance, settings, auth, arcade | move, two-phase | high |
| P17 | HTML partials per feature | move | high |
| P18 | CSS per feature, with visual regression | move, two-phase | xhigh |
| P19 | Move network I/O out of the dialer lock | bug fix | xhigh |
| P20 | Guardrails: boundary checker, AGENTS.md, Cursor rules, README | docs and tooling | high |

The end state: each feature lives in one folder (backend `features/<name>/`, frontend `static/features/<name>/`, holding that feature's JS, HTML partial and CSS together), shared plumbing lives in `shared/` and `static/core/`, and `web/` holds only HTTP glue.

---

## P0: Baseline, hygiene, standing rules

**Before:** your own changes are committed or stashed.
**You check:** `python server.py` starts; the app loads at http://127.0.0.1:8000.

```markdown
# P0: Baseline, hygiene and standing rules for a refactor chain

You are the first step of a 21-step, one-commit-per-step refactor of this repo (Python 3.10 stdlib http.server backend, vanilla JS ES modules in /static, Windows + PowerShell, repo inside OneDrive). This step changes no runtime behavior. It creates the safety rails every later step relies on.

## Preconditions (check first; on failure STOP and report)
1. `git status --porcelain` lists nothing except line-ending-only changes. Prove it: `git diff --ignore-cr-at-eol --stat` must be empty. If it shows content changes, STOP and list them; the user must commit them first.
2. Run `python -c "import twilio, zoneinfo"`. If it fails, run `pip install -r requirements.txt` and retry. Do not add packages to requirements.txt.

## Do
1. Create branch `refactor/feature-slices` from the current HEAD.
2. Line endings:
   - Create `.gitattributes` containing exactly:
     `* text=auto`
     `*.png binary`
     `*.ico binary`
   - Run `git add --renormalize .`, then `git status`.
   - If files changed only by line endings, commit them alone as `chore(P0): normalize line endings`. Verify with `git diff --cached --ignore-cr-at-eol --stat` (must be empty) before committing.
   - If nothing changed, just keep `.gitattributes` for the main commit.
3. Untrack generated files that `.gitignore` already ignores (keep them on disk): `git rm -r --cached __pycache__` and `git rm --cached call_log.csv`. Check `git ls-files | Select-String "__pycache__|\.pyc$|call_log.csv"` returns nothing.
4. Make tests discoverable:
   - Create an empty `tests/__init__.py`.
   - Copy (do not move) `Claude outputs/example_leads.csv` to `tests/fixtures/example_leads.csv`.
   - In `tests/test_transcript_storage/part_1.py`, change the fixture path from `Path(__file__).resolve().parents[2] / "Claude outputs" / "example_leads.csv"` to `Path(__file__).resolve().parents[1] / "fixtures" / "example_leads.csv"`. Change nothing else in that file.
5. Create `.cursor/rules/refactor-chain.mdc` with front matter `alwaysApply: true` and a one-line `description`, plus the STANDING RULES below, verbatim.
6. Create `docs/refactor/LOG.md` with a title, one line explaining it is the log of the P0–P20 chain, and a `## P0` entry (template under Finish).

## STANDING RULES (copy verbatim into .cursor/rules/refactor-chain.mdc)
- Work only on branch `refactor/feature-slices`. One prompt = one commit, message `refactor(Pnn): <summary>`; P0 may add one extra line-ending commit.
- Start of every prompt: `git status --porcelain` must be empty, and `docs/refactor/LOG.md` must contain an entry for the previous prompt. Otherwise STOP.
- Behavior-preserving unless the prompt explicitly says it changes behavior. No drive-by fixes. Anything you notice goes under "Noticed, not fixed" in the LOG entry.
- Read every file listed under "Read first" fully before editing anything.
- Run `python -m unittest discover -v` before your first edit (record the count) and after your last edit. All tests must pass. The count may drop only by tests the prompt explicitly names as removed.
- Tests may have their import lines and patch targets updated when code moves. Never weaken, delete or rewrite an assertion unless the prompt names that test.
- Move whole files with `git mv` so history follows. When merging several files into one, keep the code text as-is (only imports and `self`/name references may change), and state the merge in the LOG.
- Before deleting any symbol or file, prove it is unused: search .py, .js, .html, .css, tests, scripts and docs, including string literals (route paths, DOM ids, event names, getattr). Paste the search command and its empty result into the report.
- No new runtime dependencies. No reformatting of code you did not change. Keep each edited file's existing line-ending style.
- Never open, print, copy or modify `.env`. Never print secrets.
- If the prompt's description of the code does not match what you find, STOP and report the mismatch instead of improvising.
- Finish every prompt with: a report table (check | command | PASS/FAIL), the list of files changed, the LOG entry, and the commit.

## Verify (report each as PASS/FAIL)
- [ ] `python -m unittest discover -v` runs 37 tests, all OK. Before this change it ran 0; say so.
- [ ] `git ls-files` contains no `__pycache__`, `.pyc` or `call_log.csv`; the files still exist on disk.
- [ ] `git diff HEAD~1 --ignore-cr-at-eol --stat` (or against the commit before P0) shows only: `.gitattributes`, `.cursor/rules/refactor-chain.mdc`, `docs/refactor/LOG.md`, `tests/__init__.py`, `tests/fixtures/example_leads.csv`, `tests/test_transcript_storage/part_1.py`, and the untracked-file removals.
- [ ] `python -c "import server"` succeeds (import only; do not start the server).

## Finish
LOG entry format (reuse for every prompt):
## Pnn: <title>
- Date, commit hash (fill in after committing, then amend), test count before → after
- What changed (bullets, file paths)
- Moved/merged map (old → new), if any
- Noticed, not fixed
Commit as `refactor(P0): baseline, test discovery, standing rules`.
```

---

## P1: Fix local store data loss

**You check:** add a prospect in the UI, restart the server, and confirm it is still there. `crm_data/` now holds `prospects.json`, and your old part files are in `crm_data/legacy-parts-*/`.

```markdown
# P1: Make local JSON persistence crash-safe and fail-closed (prospects + metrics)

Follow .cursor/rules/refactor-chain.mdc. This prompt CHANGES behavior on purpose: storage format and failure handling only.

## The bug (reproduced by an audit)
- `crm_store/leads/parts.py` shards prospects into `crm_data/part-NN.json` files capped at 150 lines (`PART_LINE_LIMIT`). The cap came from a code-style rule leaking into the data format.
- `write_lead_parts` writes parts one at a time (not atomic across parts), then unlinks any part it did not write.
- `StorageMixin.load` (`crm_store/leads/storage.py`) catches `OSError`/`JSONDecodeError` and sets `self.leads = []`.
- Together: one truncated part → the store loads empty → the next save writes `part-01.json` and deletes every other part. Repro: 30 leads, truncate the last part, reload → 0; add one → 1 lead on disk.
- `core/metrics_store.py` has the same pattern: a corrupt `metrics.json` is ignored, and the next `bump()` overwrites it.

## Read first
`crm_store/leads/storage.py`, `crm_store/leads/parts.py`, `crm_store/leads/records.py`, `crm_store/leads/__init__.py`, `core/metrics_store.py`, `routes/runtime.py` (CRM_PATH, METRICS_PATH, configure), `supabase_store/transcripts/migrate.py`, `tests/test_transcript_storage/part_1.py` (find `test_a_directory_of_part_files_reloads_as_one_list`).

## Step 1: reproduce before fixing
Write a throwaway script in the system temp dir, not in the repo. It creates `CRMStore(<tmp>/crm)`, adds 30 leads (`add_lead({"name": f"Lead {i}", "phone": f"+1202555{i:04d}"})`), truncates the last `part-*.json` by 20 bytes, reloads, adds one lead, reloads, and prints the count. Expect 1. Do the same for `MetricsStore` with a truncated file. Paste both outputs.

## Required behavior
New module `core/json_file.py` (about 60–90 lines), used by both stores. No duplicated write logic.
- `write_json_atomic(path, data)`: write `<path>.tmp`, `flush()` + `os.fsync()`. If `<path>` exists and parses, copy it to `<path>.bak` (exactly one backup). Then `os.replace(tmp, path)`. On `PermissionError` (OneDrive holding the file), retry up to 5 times with backoff 0.1, 0.2, 0.4, 0.8, 1.6 s, then raise `OSError` with a clear message.
- `read_json_fail_closed(path, default_factory)`:
  1. Missing file → `default_factory()`.
  2. Parses → value.
  3. Fails to parse → copy it to `<stem>.corrupt-<UTC yyyymmddThhmmssZ><suffix>` (never delete it), log `core.debug_log.debug_event("error", ...)`, and try `<path>.bak`.
  4. `.bak` parses → value.
  5. Otherwise raise `CorruptStoreError(OSError)`, naming both paths.
- `CorruptStoreError` is defined in `core/json_file.py`.

Prospects (`CRMStore`; `routes/runtime.py` passes a directory path):
- Canonical file: `<dir>/prospects.json`, a JSON array of lead dicts. The lead dict shape is unchanged.
- Load order:
  1. `prospects.json` exists → `read_json_fail_closed`.
  2. Else, legacy `part-*.json` files exist → read ALL of them. If ANY fails to parse, raise `CorruptStoreError` and touch nothing. On success, write `prospects.json` atomically, then MOVE (never unlink) the parts into `<dir>/legacy-parts-<UTC timestamp>/`.
  3. Else → empty list.
- Never fall back to an empty list when data files exist. If the constructor raises there is no instance, so nothing can be saved. Do not add a degraded mode.
- The single-file branch (`CRMStore` given a `.json` path, see `_stores_parts`) uses the same helpers.
- In `parts.py`, keep only what the legacy read needs. Delete `PART_LINE_LIMIT`, `lead_chunks`, `json_line_count` and `write_lead_parts` after proving they are unused.

Metrics (`core/metrics_store.py`): `load()` uses `read_json_fail_closed`; `save()` uses `write_json_atomic`. Missing file → current defaults.

## Do not
- Touch `supabase_store/`, `twilio_calls/`, `routes/` or `static/`.
- Change `CRMStore`'s public surface: `leads`, `lock`, `revision`, `load`, `save`, `expire_due`, `snapshot`, `timezone_groups`, `csv_bytes`, `add_lead`, `add_csv`, `set_status`, `append_transcript`, `append_call_log`, `remove`.
- Restructure the mixins.

## Tests: add `tests/test_local_store.py` (temp dirs only)
1. The 30-lead truncation scenario: after the fix, the store either recovers from `.bak` with all 30 or raises `CorruptStoreError`. In both cases no file is deleted.
2. A legacy part directory migrates to `prospects.json`; the parts are moved into `legacy-parts-*/`.
3. A legacy directory with one corrupt part raises `CorruptStoreError`; all parts are untouched.
4. `os.replace` raising `PermissionError` twice, then succeeding (monkeypatch), still saves.
5. Metrics: corrupt file plus good `.bak` → recovers. Both corrupt → raises. Missing → defaults.
6. An empty directory → empty store; the first save creates `prospects.json`.
If `test_a_directory_of_part_files_reloads_as_one_list` conflicts with the new behavior, change it to assert the legacy-migration behavior. This test is explicitly allowed to change.

## Verify (PASS/FAIL each)
- [ ] Step 1 script re-run: no data lost.
- [ ] Full suite passes; count = previous + new tests.
- [ ] `git diff --stat` touches only `crm_store/leads/storage.py`, `crm_store/leads/parts.py`, `core/metrics_store.py`, `core/json_file.py`, `tests/test_local_store.py`, possibly `tests/test_transcript_storage/part_1.py`, and the LOG.
- [ ] By reading, `supabase_store/transcripts/migrate.py` still receives correct `CRMStore(path).leads` and `MetricsStore(path).data`. Do not run the migration.
Commit `refactor(P1): crash-safe, fail-closed local JSON storage`.
```

---

## P2: Characterization safety net

**You check:** nothing in the app changes. Glance at the new test files to confirm they read like a description of current behavior.

```markdown
# P2: Characterization tests that pin current behavior before files move

Follow .cursor/rules/refactor-chain.mdc. TESTS AND A CHECK SCRIPT ONLY: no production code changes. These tests describe what the app does today, including oddities, so later moves can prove nothing changed. Do not "fix" anything you find. Log it.

## Read first
`server.py`, `routes/runtime.py`, `routes/http.py`, `routes/hooks.py`, `routes/ui/__init__.py`, `routes/ui/account.py`, `routes/ui/read.py`, `routes/ui/write.py`, `twilio_calls/client/calls.py` (`validate_webhook`, `_create_call`), `twilio_calls/token/start.py`, `twilio_calls/token/voice.py`, `twilio_calls/webhooks/dispatch.py`, `twilio_calls/webhooks/pickup.py`, `twilio_calls/transcript/ended.py`, `twilio_calls/dialer/state.py`, all of `tests/test_dialer_session/` (reuse its patching patterns for Twilio and threads), `static/app-shell/*.html`, `static/js/main.js`.

## Build
1. `tests/harness.py`: the ONLY place tests import app internals for HTTP tests, so later prompts update one file.
   - `start_app(tmpdir, env_lines)`: writes a temp `.env`, points `routes.runtime` CRM_PATH, METRICS_PATH and ENV_PATH at tmpdir (set the module attributes before `AppRuntime().configure()`), starts `make_app_handler(runtime)` on `ThreadingHTTPServer(("127.0.0.1", 0))` in a daemon thread. Returns an object with `.url`, `.runtime`, `.request(method, path, body=None, headers=None) -> (status, headers, bytes)` and `.close()`.
   - `start_hooks(runtime)`: the same for `make_hook_handler`.
   - `sign(auth_token, url, params)`: computes `X-Twilio-Signature` with the algorithm in `ClientMixin.validate_webhook`.
   - `fake_twilio()`: a context manager that patches every place `twilio_request` is called (find them with grep; patch where it is looked up). It records calls and returns canned responses: `IncomingPhoneNumbers.json` → 2 voice numbers; `Calls.json` POST → `{"sid": "CA<n>"}`; hangup → `{}`. Make background threads deterministic: either patch `threading.Thread` in the calling modules to run targets synchronously, or wait on events with a 2 s timeout. No bare `sleep` over 0.2 s.
2. `tests/test_http_routes.py` (local mode, no Supabase), one test per row, asserting status code and top-level JSON keys:
   - GET `/`: 200, HTML containing `js/main.js`.
   - GET `/api/health`, `/api/auth/config`, `/api/state`, `/api/live`, `/api/metrics`, `/api/settings`, `/api/export.csv`, `/api/voice-token` (missing settings → 400 with an error).
   - POST `/api/leads` (valid; duplicate phone → 400), `/api/import` (octet-stream CSV with 2 rows), `/api/leads/{id}/status` (`{"status":"booked"}`), `/api/timezone`, `/api/settings`, `/api/pause` while idle, `/api/stop` while idle, `/api/skip` while idle (expect 400), `/api/advance` while idle (expect 400). Unknown POST → 404.
   - DELETE `/api/leads/{id}` (200) and an unknown id (404).
   - Golden key sets: capture today's exact key sets of `/api/state`, `/api/live` and `/api/settings` responses as literal Python sets in the test. Comment that they were captured in P2.
   - Status codes for error paths exactly as today: ValueError → 400, OSError on POST → 500, OSError on GET reads → 502. Use a store whose methods raise to trigger them.
3. `tests/test_call_flow.py` (local mode, `fake_twilio`, settings complete with `PUBLIC_BASE_URL=https://example.test`):
   - POST `/api/start` → 200 with `client_call_token`.
   - Signed POST `/hooks/voice` with `CallToken` → 200 TwiML containing `<Conference`.
   - A prospect call is created (fake_twilio saw `Calls.json`).
   - Signed GET `/hooks/<token>/answer` → TwiML.
   - Signed POST `/hooks/<token>/machine` with `AnsweredBy=human`.
   - Signed POST `/hooks/<token>/status` with `CallStatus=completed&CallDuration=45`.
   - `/api/state` now has `pending_outcome_id` set.
   - POST `/api/leads/<id>/status` with `{"disposition":"booked"}` → lead status `booked`; `session_stats` show dials 1, connects 1, conversations 1, meetings_booked 1.
   - Then POST `/api/stop` → `session_summary` present.
   - Separately: unsigned hook → 403; signed hook with an unknown token in local mode → handled by the local dialer (assert today's actual response).
4. `scripts/check_static.py` (stdlib only), plus `tests/test_static_assets.py` running its checks:
   - every relative `import`/`export … from` in `static/**/*.js` resolves to an existing file;
   - every named import exists as an export in the target (`export function|const|let|class NAME`, `export { a, b }`, re-exports);
   - every `byId("x")` / `getElementById("x")` / `querySelector("#x")` id exists in the concatenated `static/app-shell/*.html`, or is created in JS (`.id = "x"`);
   - every `<link href>` and `<script src>` that is not http(s) exists under `static/`.
   Print a summary and exit non-zero on failure.

## Verify (PASS/FAIL each)
- [ ] Full suite passes; report the new count.
- [ ] Run the new tests 3 times in a row: no flakes. Paste the timing; the whole suite should stay under about 10 s.
- [ ] `git diff --stat` shows only new files under `tests/`, `scripts/check_static.py` and the LOG.
- [ ] `python scripts/check_static.py` → OK.
Commit `refactor(P2): characterization tests and static asset checker`.
```

---

## P3: Security fixes

**You check:** open Settings. The auth token and API secret fields are empty, with a "saved" hint. Save another field and confirm dialing still works.

```markdown
# P3: Stop sending Twilio secrets to the browser; block cross-site requests to the local API

Follow .cursor/rules/refactor-chain.mdc. This prompt CHANGES behavior (security). Keep it to exactly these two issues.

## Issue A: secrets in GET /api/settings
`twilio_calls/settings/mixin.py` `settings_state()` returns `auth_token` and `api_secret` in plain text. `static/js/controllers/settings.js` (`applySavedSettings`) puts them into inputs. `save_settings()` already keeps the stored value when these fields are submitted blank (mixin.py, the `if not updates[...]` lines). Confirm by reading.
Fix:
- `settings_state()` returns `"auth_token": ""` and `"api_secret": ""`, and keeps `has_auth_token` / `has_api_secret`.
- `settings.js`: when `has_*` is true, set the input's placeholder to `Saved. Leave blank to keep.` and leave its value empty. Keep the show/hide buttons.
- Update the P2 golden key test only if the KEY SET changes. It should not; values change, keys do not.

## Issue B: cross-site requests (local mode has no auth)
Today any website can send a CORS "simple request" (`Content-Type: text/plain`, no preflight) to `http://127.0.0.1:8000/api/settings`, which rewrites `.env` (including `PUBLIC_BASE_URL`, where Twilio sends webhooks), or to `/api/start` / `/api/stop`. DNS rebinding can also read GET endpoints.
Fix it in the shared handler layer (`routes/http.py` `HandlerMixin`), called at the top of `do_GET`/`do_POST`/`do_DELETE` in `routes/ui/read.py` / `write.py` for paths starting with `/api/`:
- `Host` must be `127.0.0.1:<APP_PORT>` or `localhost:<APP_PORT>` (APP_PORT from `routes/runtime.py`). Otherwise 403 `{"error":"Forbidden host"}`.
- For POST and DELETE: if an `Origin` header is present, it must be `http://127.0.0.1:<APP_PORT>` or `http://localhost:<APP_PORT>`. Otherwise 403 `{"error":"Forbidden origin"}`. A missing Origin is allowed (non-browser clients).
- For POST: `Content-Type` must start with `application/json`, except `/api/import`, which must be `application/octet-stream`. Otherwise 415. Check every POST in `static/js` sends the right type (`postJson`, `request` in `api/client.js`, `debugEvent`, `importCsv`). Fix any call site that does not. A body-less `postJson` already sends JSON.
- Do not touch the Twilio hook server (`routes/hooks.py`); it has signature validation.

## Tests (add to tests/test_http_routes.py or a new tests/test_security.py)
- GET `/api/settings` never contains the saved token or secret (write known values into the temp .env).
- POST `/api/settings` with blank `auth_token` keeps the stored token.
- Cross-origin `text/plain` POST to `/api/settings` → 403 or 415, and the temp `.env` is byte-identical afterwards.
- `Host: evil.example` GET `/api/state` → 403.
- Same-origin JSON POSTs from P2 still pass unchanged.

## Verify (PASS/FAIL each)
- [ ] Full suite passes.
- [ ] `python scripts/check_static.py` OK.
- [ ] `git diff --stat` limited to `twilio_calls/settings/mixin.py`, `routes/http.py`, `routes/ui/read.py`, `routes/ui/write.py`, `static/js/controllers/settings.js`, any JS call sites fixed for content type, tests, and the LOG.
Commit `refactor(P3): mask secrets, block cross-site API requests`.
```

---

## P4: Small correctness fixes

**Before:** if you use Supabase, re-run `docs/supabase/schema.sql` in the Supabase SQL editor so `increment_dialer_metric(p_metric_key, p_increment_by, p_for_user)` exists.
**You check:** on a lead whose timezone is "Unknown", the Callback button opens the picker. Export downloads a CSV. The pool table columns line up. With Supabase, make one dial and confirm the Performance tab shows it.

```markdown
# P4: Six small, independent correctness fixes

Follow .cursor/rules/refactor-chain.mdc. This prompt CHANGES behavior, but only these items. Each gets its own test where testable. Do them in order. If one turns out bigger than described, STOP after the previous one and report.

1. Callback picker crashes for timezone "Unknown" (the default for imports without a TZ column).
   - `static/js/utils/time.js` `timezoneFor()` returns `"Unknown"`, and `Intl.DateTimeFormat` then throws `RangeError`. `controllers/outcomes.js` calls `nextBusinessCallback` with no try (the `outcomeCallButton` handler).
   - Fix: `timezoneFor(name)` maps the six US names. Otherwise it validates with `try { new Intl.DateTimeFormat("en-US", { timeZone: name }) }` and falls back to the browser's resolved time zone. `views/dialer/call-stage/stage.js` has its own copy of the zone map (`localTimeLabel`): make it use `timezoneFor` and delete the copy.
   - If `node` is available, add `tests/js/time.test.mjs` runnable with `node --test tests/js`, covering Eastern, Unknown, "", "Europe/London" and "garbage". Otherwise log that JS tests could not run.
2. Export returns 401 with Google sign-in on: `static/app-shell/metrics.html` uses `<a id="exportButton" href="/api/export.csv">`, which sends no bearer token.
   - Fix: make it `<button id="exportButton" type="button" class="button button-quiet">` with the same inner content.
   - Add `downloadFile(path, filename)` to `static/js/api/client.js`: fetch with the same auth header logic as `request`, blob, object URL, click, revoke.
   - Bind it in `static/js/controllers/csv.js`.
   - Check CSS for selectors that depend on `a#exportButton` or `a.button` and keep the look identical.
3. Supabase configured without an anon key locks the app: with Supabase storage on and no `SUPABASE_ANON_KEY`/`SUPABASE_PUBLISHABLE_KEY`, every API call returns 401 and no sign-in button shows. Fix: in `routes/runtime.py` `configure()`, raise `ValueError` with a message telling the user to set `SUPABASE_ANON_KEY` (Google sign-in is required when Supabase storage is on). `server.py` must print it and exit cleanly, not with a traceback. Test `configure()` with a fake client.
4. Supabase `add_csv` reports the wrong total: `supabase_store/leads/changes.py` does `leads.extend(additions)` and then `total = len(leads) + len(additions)`. Fix: `total = len(leads)` after the extend. Test with the existing `FakeSupabaseClient` pattern in `tests/test_transcript_storage/fixtures.py`.
5. Supabase metric counters lose concurrent updates: `supabase_store/leads/metrics.py` `_increment` does GET then POST. Commit 70366cb replaced the atomic `rpc/increment_dialer_metric` call. `docs/supabase/schema.sql` defines the function with params `p_metric_key`, `p_increment_by`, `p_for_user`.
   - Fix: `bump()` makes ONE call, `client.request("POST", "rpc/increment_dialer_metric", payload={"p_metric_key": key, "p_increment_by": amount, "p_for_user": self.user_id})`. Keep the existing validation and cache reset. Delete `_increment`.
   - If the error message contains `PGRST202` or `Could not find the function`, re-raise `OSError` telling the user to run `docs/supabase/schema.sql`.
   - Test: a fake client records exactly one request with that resource and payload.
6. Pool table header has 5 columns, rows have 6: `static/app-shell/metrics.html` (`poolTable` thead: Prospect, Company, Phone, Timezone, Transcript) vs `static/js/views/pool/index.js` (prospect, business, phone, timezone, status, transcript cells). Fix: add `<th>Status</th>` before Transcript.

## Verify (PASS/FAIL per item, plus)
- [ ] Full suite passes; `python scripts/check_static.py` OK.
- [ ] `git diff --stat` touches only files named above, tests, and the LOG.
Commit `refactor(P4): callback tz crash, export auth, anon-key guard, csv total, atomic metrics, pool header`.
```

---

## P5: Calling-hours decision (pick one variant)

The Settings dialog collects calling hours, but since commit 70366cb nothing enforces them. Before 70366cb, leads with timezone "Unknown" were never auto-dialed, which is likely why enforcement was removed. Pick one variant, **delete the other from the prompt before pasting**, and run it.

**You check (A):** set the calling hours to exclude the current hour in Eastern. Eastern leads are skipped, the queue strip shows the "outside hours" count, and right-click dialing still works.
**You check (B):** the calling-hours inputs are gone from Settings.

```markdown
# P5: Calling hours: make the setting real (VARIANT A) or remove it (VARIANT B)

Follow .cursor/rules/refactor-chain.mdc. This prompt CHANGES behavior.

## Read first
`core/dialer_session.py` (`local_time`, `within_calling_window`, `TIMEZONE_NAMES`), `twilio_calls/lifecycle/queue/slots.py`, `twilio_calls/lifecycle/queue/timing.py` (`_check_calling_window`), `twilio_calls/dialer/state.py`, `twilio_calls/settings/defaults.py`, `twilio_calls/settings/mixin.py`, `static/app-shell/dialogs.html` (calling hour inputs), `static/js/controllers/settings.js`, `docs/supabase/setup.md` (line about calls not being blocked), and the removed code: `git show 70366cb -- twilio_calls/lifecycle/queue/slots.py twilio_calls/dialer/state.py`.

## VARIANT A: enforce calling hours (recommended)
- Auto-dial (`fill_slots` pool selection) only picks leads for which `within_calling_window(tz, start, end)` is true. Read start/end from `self.settings` exactly as the removed code did.
- Leads with an Unknown or unrecognized timezone use the server machine's local time zone (`datetime.now().astimezone().tzinfo`) instead of being excluded. Implement this inside `core/dialer_session.py` as an explicit `fallback_zone` parameter of `within_calling_window`. Update its existing test for "Unknown" to the new rule; this test is explicitly allowed to change.
- Manual dials (`_claim_manual_lead`, right-click Dial) stay allowed: a human chose them.
- `public_state` gets `skipped_outside_hours` (count of pool leads currently outside hours), and `next_lead` skips them, as in the removed code. Show the count in the queue strip (`static/js/views/dialer/queue.js`) as ` · N outside calling hours` when N > 0.
- When the pool is non-empty but every lead is outside hours, set `last_event` to "All remaining prospects are outside calling hours", and let the existing 60 s `_check_calling_window` timer re-try.
- Update `docs/supabase/setup.md` to describe the rule.
- Update the P2 golden key set for `/api/state` and `/api/live` to include `skipped_outside_hours`. This is explicitly allowed.
- Tests: an Eastern lead outside hours is not dialed; inside hours it is; an Unknown lead uses the fallback zone; a manual dial outside hours still dials.

## VARIANT B: remove the setting
- Delete `CALLING_START_HOUR` and `CALLING_END_HOUR` from defaults, validation, `settings_state`, `public_state` settings, `save_settings`, `.env.example`, the dialog inputs and `settings.js`.
- Delete `within_calling_window` and `local_time` if they become unused, along with their test (explicitly allowed).
- Keep `_check_calling_window` only if something else needs the periodic refill. Otherwise delete it and its timer fields, after proving them unused.
- Update the P2 golden key set for `/api/settings` (explicitly allowed).
- `docs/supabase/setup.md`: state plainly that the dialer does not enforce calling hours.

## Verify (PASS/FAIL each)
- [ ] Full suite passes; `python scripts/check_static.py` OK.
- [ ] Changes limited to the files listed above, tests, and the LOG.
Commit `refactor(P5): calling hours <enforced|removed>`.
```

---

## P6: Delete dead code

**You check:** a full dial session works end to end: start, pickup, skip or hang up, disposition, stop, summary dialog.

```markdown
# P6: Delete dead code before moving anything

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. For EVERY item: (1) prove it is dead with searches across .py/.js/.html/.css/tests/scripts/docs and paste them, (2) delete it, (3) re-run the suite. If an item turns out to be live, skip it and log why.

## Items (verified dead by the audit; re-verify each)
1. Manual "enter live line" path. No server code ever sets a call's state to `"listening"`; only a test does. And `_transfer` cannot run: it is a `@staticmethod` with a `self` parameter (TypeError).
   - Delete `twilio_calls/webhooks/live.py` (`enter_live_line`, `_select_human`) and its `LiveMixin` from `twilio_calls/webhooks/__init__.py`.
   - Delete `_transfer` in `twilio_calls/client/calls.py`.
   - Delete the `"winner"` branch in `twilio_calls/webhooks/dispatch.py`.
   - Delete the `/api/enter-live` branch in `routes/ui/write.py`.
   - Delete `"listening"` in the tuple checks in `twilio_calls/dialer/state.py` and `twilio_calls/lifecycle/controls.py`.
   - Frontend: the `enterLiveButton` handler in `static/js/controllers/dialer/bindings.js`; the `waitingCall`/`"listening"`/`enterLiveButton` logic in `static/js/views/monitor/index.js`; `"listening"` in `static/js/views/dialer/card.js`; `enteringLiveLine` in `static/js/store/state.js`; the `enterLiveButton` element in `static/app-shell/dialer.html`; CSS rules for `.monitor-enter-live` and `[data-state="listening"]`.
   - Removed tests (explicitly allowed): `test_rep_can_manually_enter_listening_line`.
2. Answer-detection timer that is never started: `answer_detection_timer` is only ever set to `None`. Delete `_answer_detection_timeout` in `twilio_calls/webhooks/pickup.py`, the key in `_new_call` (`twilio_calls/token/start.py`), and every cancel block for it (`pickup.py`, `transcript/ended.py`). Removed test (explicitly allowed): `test_slow_answer_detection_does_not_drop_the_line`.
3. `CallStatus == "answered"` branch in `twilio_calls/webhooks/dispatch.py`. Twilio's CallStatus is never `answered` (the answered event arrives as `in-progress`; `debug-session.log` shows this). Delete the branch; `in-progress` keeps falling through to the existing "OK" return.
4. Agent `answer` branch in `dispatch.py` (`action == "answer" and call["kind"] == "agent"`). Delete it ONLY IF you prove no code launches an agent call through the REST API (`_launch_call`/`_create_call` are only called for prospects). The browser agent call enters via `/hooks/voice`. If you cannot prove it, skip and log.
5. `hydrate_env_from_supabase` in `supabase_store/transcripts/settings_io.py`, plus its exports in `supabase_store/transcripts/__init__.py` and `supabase_store/__init__.py`.
6. The unused `migrate` parameter of `AppRuntime.configure` (`routes/runtime.py`) and `migrate=True` in `server.py`.
7. The no-op line `result["current_streak"] = result.get("best_streak", 0)` in `core/dialer_session.py` `session_summary` (the key is popped two lines later).
8. Frontend checks for call state `"connecting"`, which the server never produces: `static/js/views/dialer/index.js` (the `target` computation) and `static/js/views/dialer/queue.js`. Remove only the `"connecting"` alternative; keep the rest of each expression.
9. Unused imports in every file you touched (for example `crm_store/statuses.py` imports csv, json, threading, uuid, Decimal, StringIO and Path and uses none). Remove only unused imports in files this prompt touched.

## Do not
- Delete `within_calling_window` / `local_time` (P5 decided their fate).
- Change any live behavior.

## Verify (PASS/FAIL each)
- [ ] Full suite passes; count = previous − exactly the tests named above.
- [ ] `python scripts/check_static.py` OK.
- [ ] `rg -n "listening|enter-live|enterLive|_transfer|answer_detection|hydrate_env" -g "!docs/refactor/**"` → no hits (docs/refactor excluded).
Commit `refactor(P6): remove dead code paths`.
```

---

## P7: `shared/` kernel

**You check:** the server starts; the dialer and the Prospects tab work.

```markdown
# P7: Create the shared/ kernel and point every importer at it

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving move. Target: `shared/` holds plumbing used by more than one feature and imports nothing from `features/`, `web/`, `routes/`, `twilio_calls/`, `crm_store/` or `supabase_store/`.

## Read first
`core/debug_log.py`, `core/json_file.py`, `crm_store/statuses.py`, `core/dialer_session.py` (`TIMEZONE_NAMES`), `crm_store/csv_io/fields.py` (`_timezone` uses `TIMEZONE_ALIASES`, `UTC_OFFSET_ZONES`, `TIMEZONE_ABBREVIATION`), `twilio_calls/settings/defaults.py` (`read_env`, `write_env`), `supabase_store/client/session.py`, `supabase_store/client/pool.py`, `supabase_store/client/__init__.py`, `supabase_store/__init__.py`, `scripts/migrate_to_supabase.py`. Then grep every importer of each symbol below.

## Moves
- `shared/__init__.py`: empty.
- `shared/debug_log.py` ← `git mv core/debug_log.py`. Note: `LOG_PATH` is computed from `__file__` (parent of parent = repo root). It must still resolve to `<repo>/debug-session.log`; verify and adjust only that expression if needed.
- `shared/json_file.py` ← `git mv core/json_file.py` (from P1).
- `shared/time.py` (new, about 50 lines): `utc_now` (from `crm_store/statuses.py`); `TIMEZONE_NAMES` (from `core/dialer_session.py`); `TIMEZONE_ALIASES`, `UTC_OFFSET_ZONES`, `TIMEZONE_ABBREVIATION` (from `crm_store/statuses.py`). Move the definitions; do not copy them.
- `shared/env.py` (new): `read_env(path, extra_keys=())` and `write_env(path, updates, defaults=None)`, moved from `twilio_calls/settings/defaults.py`.
  - Today `read_env` iterates `DIALER_DEFAULTS.keys()` and `write_env` falls back to `DIALER_DEFAULTS[key]` for blank values. Keep the exact behavior by having the settings code pass `extra_keys=DIALER_DEFAULTS.keys()` and `defaults=DIALER_DEFAULTS`.
  - Every caller (grep) must pass them, so results stay byte-identical. Add a test proving `read_env`/`write_env` output is unchanged for a sample `.env`, including `OPENING_SCRIPT` JSON quoting.
- `shared/supabase.py` (new): `SupabaseClient` and `_ConnectionPool`, merged from `supabase_store/client/session.py` and `pool.py`. Delete those two files.
  - `supabase_store/client/keys.py` stays for now; P9 and P10 empty it. Make `supabase_store/client/__init__.py` re-export only what still lives in that package.
- Update EVERY importer to the new paths, including tests and `scripts/`. No compatibility shims: old modules that become empty are deleted (`core/__init__.py` stays only if `core/dialer_session.py` or `core/metrics_store.py` remain, which they do).

## Verify (PASS/FAIL each)
- [ ] Full suite passes, same count + the new env test.
- [ ] `rg -n "from core.debug_log|from core.json_file|crm_store.statuses import .*utc_now|supabase_store.client.session|supabase_store.client.pool"` → no hits.
- [ ] `python -c "import shared.time, shared.env, shared.supabase, shared.debug_log, shared.json_file"` works, and `rg -n "^from (features|web|routes|twilio_calls|crm_store|supabase_store)|^import (features|web|routes|twilio_calls|crm_store|supabase_store)" shared` → no hits.
- [ ] `python -c "import server"` works.
Commit `refactor(P7): shared kernel (debug_log, json_file, time, env, supabase)`.
```

---

## P8: Single vocabulary

**You check:** the status dropdowns, status filter, pie chart legend and disposition buttons look and behave as before.

```markdown
# P8: One source of truth for statuses, dispositions, call states, metric keys and timezones

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving consolidation.

## Current copies (audit; re-grep to confirm)
- Statuses: `crm_store/statuses.py` `STATUSES`; `twilio_calls/lifecycle/outcome.py` (two inline tuples, in `choose_outcome` and `update_status`); `static/js/utils/format.js` `STATUS_STYLES`; `static/js/controllers/add-prospect.js` (inline list); `static/js/views/prospects-table/rows.js` (inline list); `static/js/views/metrics/charts.js` (inline list); `static/app-shell/metrics.html` (`statusFilter` options).
- Dispositions: `core/dialer_session.py` `DISPOSITION_TO_STATUS`; outcome → metric map inline in `outcome.py` `choose_outcome`; JS buttons in `controllers/outcomes.js`; key order in `controllers/keyboard.js`.
- Metric keys: `supabase_store/client/keys.py` `METRIC_KEYS`; `docs/supabase/schema.sql` (three CHECK lists + the function body).
- Dialer stages: `core/dialer_session.py` `STAGES`. Call states are produced in `twilio_calls/**` (`creating`, `calling agent`, `ringing`, `live`, `ended`, `cancelled`, `skipped`).
- Timezone map: `shared/time.py` `TIMEZONE_NAMES`; `static/js/utils/time.js` `timezoneFor`.

## Build
1. `shared/vocabulary.py`, pure data plus tiny helpers:
   - `STATUSES`: ordered list of dicts `{key, label, tone, color}` in the JS display order (new, call, booked, interested, disqualified, do_not_call), with labels and tones copied from `format.js` `STATUS_STYLES`.
   - `STATUS_KEYS` (tuple), `OUTCOME_STATUSES` (all but `new`).
   - `DISPOSITIONS`: ordered list `{key, status, label, shortcut}` matching today's buttons and keyboard order (booked→booked, callback→call, not_interested→disqualified, no_answer→call, do_not_call→do_not_call). Use the button labels from `static/app-shell/dialer.html`.
   - `OUTCOME_METRIC`: the map in `choose_outcome`, default `disqualified`.
   - `METRIC_KEYS`, `DIALER_STAGES`, `CALL_STATES`.
   - `client_payload()` → dict for the browser, including `timezones` from `shared/time.py`.
2. Python: replace every copy above with imports from `shared/vocabulary.py`. Keep membership semantics identical. Python code that only checks membership must not depend on order.
3. Browser delivery without an extra request: in `routes/http.py` `send_app_page`, insert `<script id="app-vocabulary" type="application/json">…</script>` immediately before `</head>`. Escape `</` as `<\/`.
4. `static/js/utils/vocabulary.js` reads and parses that element once and exports `STATUSES`, `STATUS_KEYS`, `STATUS_LABELS`, `STATUS_STYLES`, `DISPOSITIONS`, `TIMEZONE_ZONES`. `format.js` re-derives `STATUS_LABELS`/`STATUS_COLOR_VARS` from it and keeps exporting the same names, so importers do not change. Replace the inline lists in add-prospect.js, rows.js and charts.js, and the zone map in `time.js`. Generate the `statusFilter` options at startup from `STATUSES` (keep the `all` option first), and remove them from `metrics.html`.
5. `docs/supabase/schema.sql` cannot import Python. Add a comment above each CHECK list: `-- keep in sync with shared/vocabulary.py METRIC_KEYS (enforced by tests/test_vocabulary.py)`.
6. `tests/test_vocabulary.py`:
   - every key set used in Python equals the vocabulary;
   - every metric-key list parsed out of `schema.sql` equals `METRIC_KEYS`;
   - GET `/` contains `app-vocabulary` with valid JSON;
   - a regex scan of `static/**/*.js` finds no hardcoded status array (a literal array containing both `"do_not_call"` and `"disqualified"`) outside `utils/vocabulary.js`.

## Do not
Change labels, colors, ordering in the UI, or the API payloads (P2 golden keys must still pass unchanged).

## Verify (PASS/FAIL each)
- [ ] Full suite passes; `python scripts/check_static.py` OK.
- [ ] `rg -n "\"do_not_call\"" --type py --type js` shows definitions only in `shared/vocabulary.py`, plus comparisons/usages that refer to a single key, not lists. Paste the hits.
Commit `refactor(P8): single vocabulary for statuses, dispositions, metrics, timezones`.
```

---

## P9: `features/metrics/` slice

**You check:** the Performance tab numbers match before and after.

```markdown
# P9: Metrics feature slice

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving move.

## Target
features/__init__.py                    (empty)
features/metrics/__init__.py            public API + MetricsStore Protocol
features/metrics/store_local.py         ← git mv core/metrics_store.py
features/metrics/store_supabase.py      ← git mv supabase_store/leads/metrics.py

## Do
- `features/metrics/__init__.py` exports `LocalMetricsStore` (rename the class `MetricsStore` → `LocalMetricsStore`), `SupabaseMetricsStore`, and a `typing.Protocol` named `MetricsStore` with `bump(key, amount=1)`, `save_session(session)`, `recent_sessions(limit=5)` and `snapshot(days=7)`. Signatures come from the current classes.
- Both stores implement all four methods (verify). So remove the defensive `hasattr(self.metrics, "save_session")` in `twilio_calls/dialer/core.py` `_save_session` and `hasattr(self.metrics, "recent_sessions")` in `twilio_calls/lifecycle/controls.py` `stop`. Keep the `if self.metrics` None checks.
- Update all importers: `routes/runtime.py`, `supabase_store/leads/__init__.py`, `supabase_store/__init__.py`, `supabase_store/transcripts/migrate.py`, tests. External code imports only from `features.metrics`, never from `features.metrics.store_*`, except tests of a specific store.
- `METRIC_KEYS` already lives in `shared/vocabulary.py` (P8). Make sure `store_supabase.py` imports it from there.

## Verify (PASS/FAIL each)
- [ ] Full suite passes.
- [ ] `rg -n "core.metrics_store|supabase_store.leads.metrics|MetricsStore\(" ` → only `features/metrics/**` and tests.
- [ ] `python -c "import server"` works.
Commit `refactor(P9): metrics feature slice`.
```

---

## P10: `features/settings/` slice

**You check:** open Settings, change Session goal, save, reload the page, and confirm it persisted. Start a dial session to confirm the Twilio credentials still load.

```markdown
# P10: Settings feature slice; remove the storage → dialer import

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving.

Today settings logic lives in five places: `twilio_calls/settings/defaults.py` (DIALER_DEFAULTS, `_preferences` validation, TWILIO_API), `twilio_calls/settings/mixin.py` (`_values`, `settings_state`, `save_settings` on the dialer), `supabase_store/transcripts/settings_io.py` (`load_app_settings`, `save_app_settings`), `supabase_store/client/keys.py` (`REMOTE_SETTING_KEYS`, `SETTINGS_ROW_ID`; it imports `twilio_calls.settings`, so importing storage loads the entire dialer and the twilio SDK), `routes/runtime.py` (`persist_settings`, `reload_settings`), and a duplicate preferences block in `twilio_calls/dialer/state.py`.

## Read first
All files named above, plus `tests/test_dialer_session/part_2.py` and the P2/P3 settings tests.

## Target
features/settings/__init__.py   public API (only names other modules need)
features/settings/model.py      DIALER_DEFAULTS, TWILIO_KEYS, normalize_preferences (was _preferences),
                                settings_view(values, storage_name, account_email)   (body of settings_state),
                                public_preferences(values)   (the block in dialer/state.py, same keys),
                                apply_form(current_values, form) -> (updates, preferences)   (logic of save_settings)
features/settings/store.py      REMOTE_SETTING_KEYS, SETTINGS_ROW_ID, load_local(env_path), save_local(env_path, updates),
                                load_account(client, user_id), save_account(client, values, user_id)
                                (uses shared/env.py and shared/supabase.py)

## Do
- Move code; do not rewrite it. `TWILIO_API` moves to `twilio_calls/client/http.py` (P12 will absorb it).
- Dialer mixin `twilio_calls/settings/mixin.py` becomes a thin delegate: `_values()`, `settings_state()` → `model.settings_view(...)`, `save_settings()` → `model.apply_form` + `store.save_local` or `settings_saver`. Delete `twilio_calls/settings/defaults.py`. Keep the mixin file itself; P13 removes it.
- `twilio_calls/dialer/state.py` uses `model.public_preferences(self._values())` instead of its own block.
- `routes/runtime.py` `persist_settings`/`reload_settings` call `features.settings.store`. Keep the exact error message about running `schema.sql`.
- Delete `supabase_store/transcripts/settings_io.py` and `supabase_store/client/keys.py`, after moving `METRIC_KEYS` users to `shared/vocabulary.py` (P8). Fix the `__init__` exports.
- Rules: `features/settings/*` may import only `shared/*`. Nothing in `supabase_store/` may import `twilio_calls`.

## Verify (PASS/FAIL each)
- [ ] Full suite passes; the P2 golden `/api/settings` and `/api/state` key sets are unchanged.
- [ ] `python -c "import sys, supabase_store; print('twilio_calls' in sys.modules, 'twilio' in sys.modules)"` prints `False False`. Before this prompt it printed `True True`; say so.
- [ ] `rg -n "_preferences|settings_io|client.keys|DIALER_DEFAULTS" -g "!features/settings/**" -g "!docs/**"` shows only imports from `features.settings`.
Commit `refactor(P10): settings feature slice`.
```

---

## P11: `features/prospects/` slice (two-phase)

**You check:** import a CSV, add a prospect manually, change a status from the table, delete one, export, and confirm the transcript viewer still opens. With Supabase, do the same signed in.

```markdown
# P11: Prospects feature slice: one rules layer, two thin storage backends

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE: do Phase A, then STOP and wait for the user to reply `go`.

## Today (audit)
- Local: `crm_store/` (11 files). `CRMStore = RecordMixin + StorageMixin`; CSV in `csv_io/{fields,parse,export}.py`; header constants in `crm_store/statuses.py`; `leads/manual.py` (`build_manual_lead`); `leads/parts.py` (legacy reader from P1).
- Supabase: `SupabaseCRMStore = ChangeMixin (supabase_store/leads/changes.py) + RecordMixin (supabase_store/leads/records.py) + TranscriptMixin (supabase_store/transcripts/mixin.py)`. It imports `parse_csv`, `build_manual_lead` and `STATUSES` from `crm_store`.
- The rules are copied in both backends: `set_status` (90% similar), `append_transcript` and `append_call_log` (93%), expiry (`expire_due` vs `_expire`), `timezone_groups`.
- Consumers use the duck-typed surface: `snapshot()`, `add_lead`, `add_csv`, `set_status`, `append_transcript`, `append_call_log`, `remove`, `timezone_groups(leads)`, `csv_bytes()`, `revision`, `lock` (grep `crm.` and `.crm.` in twilio_calls, routes and scripts to confirm).

## Target
features/prospects/__init__.py       exports ProspectStore, LocalBackend, SupabaseBackend, CorruptStoreError (re-export), parse_csv
features/prospects/rules.py          pure functions: build_manual_lead (+ its _text/_extra_fields/_transcript), normalize_transcript_entry,
                                     normalize_call_log_record, apply_status(lead, status, scheduled_until, now),
                                     expire_callbacks(leads, now) -> changed_leads, timezone_counts(leads)
features/prospects/store.py          class ProspectStore(backend): owns lock, in-memory list, revision; implements the consumer
                                     surface above using rules.py; calls backend for persistence only
features/prospects/backend_local.py  LocalBackend(path): load_all(), persist(changed, all_leads) → atomic write of all_leads, delete(id, all_leads)
                                     (uses shared/json_file.py; legacy part migration from P1 moves here; parts.py merges in)
features/prospects/backend_supabase.py SupabaseBackend(client, user_id): load_all() (paged select, scoped), insert(new), update(lead), delete(id) -> bool
features/prospects/csv_import.py     csv_io/fields.py + csv_io/parse.py + header-word constants from crm_store/statuses.py
features/prospects/csv_export.py     ← csv_io/export.py
scripts/migrate_to_supabase.py       absorbs supabase_store/transcripts/migrate.py (its only caller)

## Behaviors to preserve exactly (write tests for each before moving, in tests/test_prospect_store_contract.py, running every case against LocalBackend AND SupabaseBackend with the existing FakeSupabaseClient pattern)
- Local loads eagerly at construction and raises CorruptStoreError then (P1). Supabase loads lazily on first use, then serves from memory (`test_snapshot_uses_memory_after_the_first_load`).
- Local persists the whole list per change. Supabase POSTs inserts in batches of 500 with `on_conflict=id`, PATCHes single leads scoped by user_id, and on DELETE raises KeyError when no row comes back.
- Expiry: Supabase writes each expired lead individually; local saves once. `revision` increments as today in each backend (count the bumps in today's code and match them).
- `add_csv` return dict (`duplicates`, `skipped`, `columns`, `added`, `total`).
- Every ValueError/KeyError message, unchanged.

## Phase A (then STOP)
Write `docs/refactor/P11-plan.md` containing:
1. A table mapping every function/method in `crm_store/**`, `supabase_store/leads/{changes,records}.py` and `supabase_store/transcripts/mixin.py` to its new home, or "deleted (duplicate of X)".
2. Every divergence between the two backends' copies (diff them), and which behavior the merged rule keeps.
3. Every consumer call site that changes.
4. The contract test list.
Commit nothing. Reply with the plan summary and wait for `go`.

## Phase B (after `go`)
1. Write the contract tests against the CURRENT classes first and run them green. This proves they describe today.
2. Build the target, switch `routes/runtime.py` (`CRMStore(CRM_PATH)` → `ProspectStore(LocalBackend(CRM_PATH))`; `SupabaseCRMStore(client, user_id=...)` → `ProspectStore(SupabaseBackend(client, user_id))`), and point the contract tests at the new classes. Same tests, green.
3. Delete `crm_store/`, plus `supabase_store/leads/` and `supabase_store/transcripts/` (after proving them empty or unused). Delete `supabase_store/` entirely if nothing remains.
4. Update test imports. `tests/test_transcript_storage/*` may switch to the new classes. Do not change assertions.

## Verify (PASS/FAIL each)
- [ ] Full suite passes (old + contract tests).
- [ ] `rg -n "crm_store|supabase_store"` → only `docs/` hits.
- [ ] `features/prospects/*` imports only `shared/*` and its own modules.
- [ ] No duplicated rule: `apply_status`, expiry and transcript/call-log normalization each exist once (paste a grep).
Commit `refactor(P11): prospects feature slice`.
```

---

## P12: Twilio adapter

**You check:** a full dial session; the debug log shows the same Twilio request/callback lines as before.

```markdown
# P12: Extract a pure Twilio adapter into features/dialer/twilio_api.py

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. Mixin files under `twilio_calls/` keep their methods but call the adapter instead of building requests, signatures and TwiML themselves.

## Read first
`twilio_calls/client/{calls,http,phone,__init__}.py`, `twilio_calls/token/{start,voice,index}.py`, `twilio_calls/transcript/live.py` (`_live_twiml`, `_start_transcription`), `twilio_calls/webhooks/dispatch.py` (inline TwiML strings), `twilio_calls/__init__.py`, and every test that patches `twilio_request`, `threading` or `_create_call` (grep).

## Build `features/dialer/__init__.py` (empty for now) and `features/dialer/twilio_api.py` (about 220 lines; no `self`, no dialer state, imports only stdlib, `twilio.jwt`, `twilio.twiml` and `shared/*`)
- Basics: `TWILIO_API`, `TwilioError`, `request(account_sid, auth_token, method, path, data=None, params=None)` (was `twilio_request`), `normalize_phone`, `escape_xml`.
- REST: `list_voice_caller_ids(sid, token) -> list[str]` (the loop in `start()`); `create_call(sid, token, data) -> call_sid` (raises TwilioError when no sid); `hangup_call(sid, token, call_sid)` (swallows TwilioError/KeyError as today).
- Webhooks: `validate_signature(auth_token, url, signature, params) -> bool` (the body of `validate_webhook`).
- Tokens: `voice_access_token(values) -> str` (the required-key check + AccessToken/VoiceGrant, same identity and ttl).
- TwiML: `hangup_twiml()`, `agent_conference_twiml(conference, agent_ended_url)` (from voice.py), `live_conference_twiml(conference, transcript_url, stream_name, start_transcription)` (from transcript/live.py; same arguments to `.transcription(...)` and `.conference(...)`).
- `TokenIndex` (moved from `twilio_calls/token/index.py`).
- `call_request_data(kind, to, from_, answer_url, status_url, machine_url)`: builds the exact dict in `_create_call`, including the AMD fields for prospects.

## Do
- Replace the implementations in the mixins with adapter calls. Mixins keep all state handling, locking and activity logging exactly as today.
- Delete `twilio_calls/client/http.py`, `phone.py` and `token/index.py` once empty. Keep re-exports in `twilio_calls/__init__.py` only for names the rest of the code still imports, and repoint those importers to `features.dialer.twilio_api` where it is a one-line change.
- Golden tests: add `tests/test_twilio_api.py` asserting byte-identical TwiML strings and identical `call_request_data` dicts versus today. Capture today's outputs by calling the OLD code first, before editing, and paste them into the test as literals.
- Update patch targets in tests (patch where the name is looked up). Assertions do not change.

## Verify (PASS/FAIL each)
- [ ] Full suite passes, including `tests/test_call_flow.py` from P2, unchanged.
- [ ] `rg -n "urllib.request|hmac|AccessToken|VoiceResponse|<Response" twilio_calls` → no hits.
Commit `refactor(P12): pure Twilio adapter`.
```

---

## P13: Collapse the dialer (two-phase)

**You check:** a full dial session, including pause/resume, skip, hang up, manual right-click dial, timezone filter, auto-advance countdown and Advance now, stop, and the summary dialog.

```markdown
# P13: Collapse TwilioDialer (22 classes in 22 files) into features/dialer/

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE.

## Today
`twilio_calls/dialer/__init__.py`: `class TwilioDialer(CoreMixin, StateMixin, SettingsMixin, ClientMixin, TokenMixin, WebhookMixin, TranscriptMixin, LifecycleMixin)`, assembled from about 20 mixin files under `twilio_calls/` that share state on `self` (for example `last_event` is written from 11 files). Plus `core/dialer_session.py` (pure session-stat and stage rules).

## Target (each file one cohesive responsibility; ONE class, at most two files)
features/dialer/__init__.py        exports Dialer, TokenIndex (re-export), and nothing else
features/dialer/engine.py          class Dialer(CallEventsMixin): construction/state fields (CoreMixin.__init__), settings access (thin SettingsMixin),
                                   session lifecycle (start, stop, pause), queue (fill_slots, manual dial, _claim_manual_lead, _pin_manual_dial,
                                   advance + calling-window timers), call control (_new_call, _next_caller, _launch_call, _create_call,
                                   _cancel_call, _hangup_call, hangup_active, skip_active), outcomes (choose_outcome, update_status,
                                   live_outcome_lead_id), activity log, token watch/release, voice_access_token wrapper
                                   — sections in that order, each under a `# --- <section> ---` comment   (~480 lines)
features/dialer/call_events.py     class CallEventsMixin: handle_client_voice, handle_webhook, _pickup, _machine_result,
                                   _call_ended, _agent_call_ended, _transcription_event, _live_twiml   (~280 lines)
features/dialer/projection.py      build_public_state(dialer), build_live_state(dialer)   (StateMixin body; Dialer.public_state/live_state delegate)
features/dialer/session_stats.py   ← git mv core/dialer_session.py
features/dialer/twilio_api.py      (from P12)

## Phase A (then STOP)
1. Run, and save the output to `docs/refactor/P13-before.txt`:
   `python -c "from twilio_calls import TwilioDialer as D; print('\n'.join(sorted(n for n in dir(D) if not n.startswith('__'))))"`
2. Write `docs/refactor/P13-plan.md`: every method of every mixin (from that list) → target file and section; every module-level helper; every importer of `TwilioDialer`, `core.dialer_session` and `twilio_calls.*` that changes; the order of operations.
3. Reply with a summary and wait for `go`.

## Phase B (after `go`)
- Move method bodies verbatim. Allowed edits: imports; the class name (`TwilioDialer` → `Dialer`, updating all importers including `routes/runtime.py` and tests); delegating `public_state`/`live_state` to `projection.py`.
- Delete `twilio_calls/` and `core/` (prove each emptied module unused first).
- Run the same `dir()` listing for `Dialer` into `docs/refactor/P13-after.txt`. The two lists must be identical, except for names you list in the report with a reason (expected: none).

## Verify (PASS/FAIL each)
- [ ] Full suite passes; P2 call-flow and route tests unchanged.
- [ ] P13-before/after method lists identical (paste the diff: empty).
- [ ] `rg -n "twilio_calls|core\.dialer_session|core\.metrics_store|from core" -g "!docs/**"` → no hits.
- [ ] `features/dialer/*` imports only `shared/*`, `features.prospects`/`features.metrics`/`features.settings` package roots, and its own modules.
- [ ] Largest file in `features/dialer/` is under 600 lines (report sizes).
Commit `refactor(P13): dialer feature slice`.
```

---

## P14: Web layer and per-feature routes (two-phase)

**You check:** every tab and action works in local mode. If you use Supabase, sign out, sign in with Google, and repeat.

```markdown
# P14: Replace routes/ (mixin handlers + if/elif chains) with web/ plumbing and per-feature route tables

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE.

## Today
`routes/http.py` (HandlerMixin: tracing, body/JSON reading, static and app page, vocabulary injection, P3 request guard), `routes/hooks.py` (Twilio server), `routes/runtime.py` (paths/ports constants, Account, AppRuntime: backend selection, per-user sessions, health, settings persist/reload), `routes/ui/{__init__,account,read,write}.py` (string if/elif dispatch for every endpoint, with error mapping copied per branch).

## Target
shared/config.py              APP_DIR, STATIC_DIR, CRM_PATH, METRICS_PATH, ENV_PATH, APP_HOST/PORT, HOOK_HOST/PORT, MAX_BODY, QUIET_HTTP
web/__init__.py
web/server.py                 HandlerMixin + make_app_handler(runtime, routes): matches (method, path) against a route table
                              (exact paths, plus patterns `/api/leads/{id}`, `/api/leads/{id}/dial`, `/api/leads/{id}/status`),
                              applies the P3 guard, opens the account, calls the handler, maps exceptions → status codes
web/accounts.py               Account + AppRuntime (from routes/runtime.py) + open_account (from routes/ui/account.py)
web/hooks.py                  ← git mv routes/hooks.py
web/system_routes.py          /api/health, /api/auth/config, /api/auth/me, /api/debug
features/dialer/routes.py     start, pause, stop, hangup, skip, advance, timezone, leads/{id}/dial, leads/{id}/status, state, live, voice-token
features/prospects/routes.py  POST /api/leads, POST /api/import, GET /api/export.csv, DELETE /api/leads/{id}
features/metrics/routes.py    GET /api/metrics
features/settings/routes.py   GET/POST /api/settings
Each routes.py exports ROUTES = [Route(method, pattern, handler, error_profile)].
A handler takes (request, account) and returns a Response (json or bytes + headers).
server.py builds the table from all ROUTES lists.

## Error mapping must match today exactly (the P2 tests pin it)
- POST: ValueError/KeyError/UnicodeDecodeError → 400; OSError → 500 "Could not persist data: …"; other → 502.
- GET reads: OSError → 502 "Could not read persistent data: …" via `report_storage_error`.
- DELETE: KeyError → 404; OSError → 500.
- `/api/voice-token`: ValueError → 400.
- `/api/settings` GET: no OSError handling today; keep it that way.
- Activity-log side effects (`record_activity("GET …" / "POST …", "web")` and the "Request rejected/failed" entries) happen at the same points.
Encode this as a small set of named error profiles (`post`, `read`, `delete`, `voice_token`), not per-route code.

## Phase A (then STOP)
Write `docs/refactor/P14-plan.md`: every endpoint today (method, path, handler code location, error behavior, activity-log behavior) → target route + error profile. Flag anything that does not fit a profile. Reply and wait for `go`.

## Phase B
Build the target, switch `server.py`, update `tests/harness.py` (the only test file that should need import changes), and delete `routes/`.

## Verify (PASS/FAIL each)
- [ ] Full suite passes; no assertion changed (show `git diff -- tests` touches only `tests/harness.py` and import lines).
- [ ] `rg -n "routes\." -g "*.py" -g "!docs/**"` → no hits; `routes/` gone.
- [ ] Every endpoint in the P14 plan appears exactly once across the ROUTES lists (add a test that asserts the full (method, pattern) set).
- [ ] No module under `features/` imports `web`.
Commit `refactor(P14): web layer and per-feature route tables`.
```

---

## P15: Frontend `core/` and `features/dialer/` (two-phase)

**You check:** a full dial session in the browser with DevTools open: no console errors, the mic test works in Settings, and the arcade effects still fire on connect and booked.

```markdown
# P15: Frontend: core/ plus the dialer feature folder

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE. No build step: plain ES modules; the static server serves any file under `static/` (see the static-serving code in `web/server.py`), and `static/app-shell/chrome.html` loads `js/main.js`. New layout: `static/core/` for shared modules, `static/features/<name>/` for everything one feature owns (its JS now; its HTML partial and CSS arrive in P17/P18).

## Today (dialer UI spread across 23 files in 9 folders)
controllers/dialer/{index,bindings,session,lead,connect}.js, controllers/{outcomes,keyboard,pool,poller}.js,
views/dialer/{index,card,controls,outcome,queue,session-goal}.js, views/dialer/call-stage/{index,stage,timer}.js,
views/monitor/index.js, views/dialogs/index.js (session summary part), features/voice/device/{index,connect,devices}.js,
features/voice/testing/index.js, plus shared helpers in utils/ and store/, and views/render.js (imports every feature's renderer).

## Target
static/core/api.js          ← api/client.js
static/core/store.js        ← store/state.js (only fields used by 2+ features stay here; see below)
static/core/dom.js          ← utils/format.js (byId, setText, initials, statusDate, formatMinutes, dayLabel; re-export STATUS_* from vocabulary)
static/core/toast.js        ← utils/notify.js
static/core/time.js, core/phone.js, core/transcript.js, core/vocabulary.js   ← utils/*
static/core/render.js       registerRenderer(fn) + render(): replaces views/render.js; features register at bind time, so core imports no feature
static/main.js               ← git mv static/js/main.js (update the <script src> in static/app-shell/chrome.html)
static/features/dialer/index.js     bindDialer(), registers its renderer, exports dialLead/startDialing for other features
static/features/dialer/controls.js  bindings.js + session.js + lead.js + connect.js merged; startDialing/dialLead share one
                                       connect-and-cleanup helper (they are near-duplicates today; keep both public behaviors identical)
static/features/dialer/view.js      views/dialer/{index,card,controls,outcome,queue,session-goal}.js
static/features/dialer/call-stage.js  call-stage/{stage,timer}.js
static/features/dialer/monitor.js   views/monitor/index.js
static/features/dialer/outcomes.js  controllers/outcomes.js + controllers/keyboard.js
static/features/dialer/voice.js     features/voice/device/*
static/features/dialer/mic-test.js  features/voice/testing/index.js
static/features/dialer/poller.js    controllers/poller.js
static/features/dialer/state.js     the S fields only the dialer uses (voice, waveform, mic test, call timer, stage memory, kept line, goal/halfway/break)

## Rules
- `core/*` imports nothing from `features/`. A feature imports `core/*`, its own files, and other features only through `features/<x>/index.js`.
- Arcade stays where it is in this prompt (P16 moves it). The dialer keeps importing it, through one import site.
- `controllers/pool.js` (timezone select) belongs to prospects/pool. Leave it for P16, but repoint its imports.

## Phase A (then STOP)
Write `docs/refactor/P15-plan.md`: every exported and internal function → target file; every `S.<field>` with the files that read or write it (grep) → stays in core/store.js or moves to features/dialer/state.js; every importer that changes. Wait for `go`.

## Phase B
Move code verbatim (imports and identifiers only). `git mv` whole files where one old file becomes one new file. Update `main.js`. Delete emptied folders.

## Verify (PASS/FAIL each)
- [ ] `python scripts/check_static.py` OK (imports resolve, named exports exist, DOM ids exist).
- [ ] Full Python suite passes.
- [ ] `rg -n "from \"\.\./\.\./features|from \"\.\./features" static/core` → no hits.
- [ ] Load http://127.0.0.1:8000 with the server running and report any console errors (use the browser tool if available; otherwise list this as a user check).
Commit `refactor(P15): frontend core and dialer feature`.
```

---

## P16: Frontend: remaining features (two-phase)

**You check:** every tab works; sign-in/out (with Supabase); add-prospect dialog; right-click Dial; transcript viewer and download; Settings save; arcade toggles persist after reload. No console errors.

```markdown
# P16: Frontend: prospects, performance, settings, auth, arcade and the app shell

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE. Same layout rules as P15: `static/core/` imports no feature; features talk only through `static/features/<x>/index.js`.

## Target
static/features/prospects/index.js        bindProspects(): wires everything below, registers its renderer and its tab hooks
static/features/prospects/table.js        views/prospects-table/{index,query,render,rows}.js
static/features/prospects/status.js       controllers/prospects.js (status change via the "prospect-status" CustomEvent, bulk delete)
static/features/prospects/add-dialog.js   controllers/add-prospect.js
static/features/prospects/csv.js          controllers/csv.js (import + export from P4)
static/features/prospects/context-menu.js controllers/prospect-menu.js (calls dialer only via features/dialer/index.js)
static/features/prospects/pool.js         views/pool/index.js + controllers/pool.js (timezone filter)
static/features/prospects/transcript-dialog.js  the transcript dialog binding from views/dialogs/index.js + openTranscript/downloadTranscript
static/features/performance/index.js      views/metrics/index.js + views/metrics/charts.js (~180 lines)
static/features/settings/index.js         controllers/settings.js
static/features/auth/index.js             controllers/auth.js
static/features/arcade/index.js           ONE class built from features/arcade/controller/{index,playback,shell}.js + fx/{audio,particles,reels}.js
                                          (today 5 mixin factories composed in controller/index.js); export the same public API
                                          (startArcade, arcadeSensory, playCue, celebrateBooked and whatever else is imported — grep)
static/core/navigation.js                 controllers/navigation.js, with registerTab(name, onShow) instead of importing renderTable/renderCallerPool
static/main.js                            only calls each feature's bind/init, in today's order

## Rules
- Replace hidden coupling with explicit hooks: `setStartNewSession` (views/dialogs) and `setUnauthorizedHandler` (api/client) become registrations in the owning feature's index.js. Keep the CustomEvent "prospect-status" or turn it into a direct call inside the prospects feature; it never leaves that feature.
- Move each remaining `S.<field>` from `core/store.js` to the feature that alone uses it.
- When done, `static/js/` contains no files (delete the folder).

## Phase A (then STOP)
Write `docs/refactor/P16-plan.md` (function → file map, S-field ownership, cross-feature calls after the move, and the startup order in main.js before/after). Wait for `go`.

## Phase B
Move verbatim; `git mv` where 1→1. For arcade, flatten the mixin chain into one class: copy each mixin's methods into the class body in the same order as today's composition (the MRO order of `ParticlesMixin(ReelsMixin(AudioMixin(PlaybackMixin(ArcadeCore))))`). Report any method name defined in more than one mixin, and keep the one that wins today.

## Verify (PASS/FAIL each)
- [ ] `python scripts/check_static.py` OK; full Python suite passes.
- [ ] `static/js/` does not exist; `rg -n "features/[a-z]+/(?!index\.js)" static/features --pcre2` shows no cross-feature deep imports (imports inside a feature's own folder are fine; filter them out and paste the remaining hits: expected none).
- [ ] Report the file count and lines per feature folder.
Commit `refactor(P16): frontend feature folders`.
```

---

## P17: HTML partials per feature

**You check:** the page looks identical; every dialog opens.

```markdown
# P17: Split the HTML shell into per-feature partials

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving.

## Today
The server concatenates `static/app-shell/chrome.html`, `dialer.html`, `metrics.html` and `dialogs.html` (see the app-page code in `web/server.py`). `metrics.html` holds the Performance panel AND the Prospects and Caller-pool panels. `dialogs.html` holds every dialog (settings, add prospect, transcript, session summary) plus the closing tags. Elements open in one partial and close in another.

## Target
static/core/shell-start.html            doctype, head, login gate, nav, opening wrappers (from chrome.html)
static/features/dialer/dialer.html
static/features/performance/performance.html
static/features/prospects/prospects.html   prospects + pool panels
static/features/settings/settings-dialog.html
static/features/prospects/dialogs.html     add-prospect + transcript dialogs
static/features/dialer/dialogs.html        session summary dialog
static/core/shell-end.html              closing tags (from the end of dialogs.html)
The server's partial list is updated to this order; also update `scripts/check_static.py` and the P2 harness if they list partials.

## Correctness rule
Before editing, save the page as served today: `GET /` → `docs/refactor/P17-before.html`. After: `P17-after.html`. Requirements:
- Byte-identical after normalizing line endings, EXCEPT that top-level `<dialog>` elements may be reordered (they render in the top layer, so position does not matter).
- Add `tests/test_app_shell.py`: parse both with `html.parser`, and assert the same sequence of (tag, id, class) for everything except `<dialog>` subtrees, plus the same multiset of `<dialog>` subtrees.
- Delete `static/app-shell/`.

## Verify (PASS/FAIL each)
- [ ] Full suite passes, including the new shell test; `python scripts/check_static.py` OK.
- [ ] `docs/refactor/P17-before.html` and `P17-after.html` are committed (they are small and document the invariant).
Commit `refactor(P17): HTML partials per feature`.
```

---

## P18: CSS per feature, with visual regression (two-phase)

**Before:** P18 needs Playwright for screenshots. It installs it into a throwaway virtual environment outside the repo. If that's not allowed on your machine, the prompt falls back to a manual screenshot checklist.
**You check:** compare the before/after screenshot folders it reports, at desktop and phone width.

```markdown
# P18: CSS by feature without changing a single pixel

Follow .cursor/rules/refactor-chain.mdc. Behavior-preserving. TWO-PHASE. Risk: the cascade. Today 14 files are linked in a fixed order (`css/01-tokens.css` … `css/09-shell.css`, then `css/linear/{shell,document,controls,monitor,metrics}.css`; see `static/core/shell-start.html`). 137 of 701 selectors are defined in 2–7 different files (for example `.dialer-run-panel` in 7 files), so later files override earlier ones.

## Target
static/core/base.css                       tokens, reset, shell/nav, layout primitives, shared components (buttons, inputs, tables, dialogs base, toast)
static/features/dialer/dialer.css          dialer panel, controls, call stage, monitor, outcome row, session goal
static/features/prospects/prospects.css    prospects table, pool table, add/transcript dialogs, context menu
static/features/performance/performance.css
static/features/settings/settings.css
static/features/arcade/arcade.css
Link order: base.css, then the feature files in the order above. The old `static/css/` is deleted.

## Method (Phase A, then STOP)
1. Visual baseline: in a temp virtualenv OUTSIDE the repo, install `playwright` and Chromium. Do not add it to requirements.txt.
   - Write the screenshot script in the system temp dir.
   - Start the app in local mode against a temp data dir seeded with 12 prospects across statuses and timezones (reuse `tests/harness.py`).
   - Capture full-page screenshots at 1440×900 and 390×844 of: login gate hidden + Dialer tab idle; Performance tab (summary and all modes); Prospects tab; Caller pool tab; Settings dialog open; Add prospect dialog open; Transcript dialog open for a lead with 3 transcript lines.
   - Save them to a temp folder named in your report.
   - If Playwright cannot be installed, STOP and give the user this exact list to screenshot manually.
2. Inventory: parse all 14 files into ordered rule blocks (respecting @media and @keyframes). Write `docs/refactor/P18-plan.md` with: each block → target file; every selector defined in more than one block, its blocks in today's order, and how the new order preserves "later wins". Where moving would break that order, merge the declarations of same-selector, same-media blocks into one block (later declarations win, duplicates removed). Flag any block you cannot place safely.
3. Wait for `go`.

## Phase B
Build the new files from the plan, update the `<link>`s, re-capture every screenshot, and pixel-diff (Pillow `ImageChops.difference`; Pillow is installed in the same temp venv). Every pair must have 0 differing pixels. If any differ, fix the CSS (usually ordering) and re-run. Never accept a diff.

## Verify (PASS/FAIL each)
- [ ] Screenshot pairs: list each with its differing-pixel count (all 0).
- [ ] `python scripts/check_static.py` OK; full suite passes.
- [ ] Report: selectors defined in more than one file, before (137) → after (target: only intentional base/feature overrides; list them).
Commit `refactor(P18): CSS per feature`.
```

---

## P19: Move network I/O out of the dialer lock

**You check:** with Supabase, during a live call the UI stays responsive (no 1–2 s freezes when a call ends or a disposition is saved).

```markdown
# P19: No network I/O while holding Dialer.lock

Follow .cursor/rules/refactor-chain.mdc. This prompt CHANGES timing, not results.

## Problem
In `features/dialer/engine.py` and `call_events.py`, `self._bump(...)` (Supabase: one RPC call after P4) and `self._save_session()` (one HTTP POST) run inside `with self.lock:`. `public_state()` (polled every 1.5 s) and every Twilio webhook also take that lock, so they wait on Supabase latency. The audit found this in today's equivalents of: `_call_ended` (connected/talk_seconds bumps, session save), `_pickup` (session save), `_machine_result` (voicemail bump), `_new_call` (dials bump + session save; called under lock from `start` and `fill_slots`), `start` (session save), `choose_outcome` (session save), `stop` (session save), and `_create_call`'s failure path (failed bump). Grep for every `_bump(` and `_save_session(` call and classify each as under the lock or not.

## Fix
- Add a small mechanism in `engine.py`: `with self._locked() as after:` acquires `self.lock` and yields a list. Code appends callables (`after.append(lambda: self._bump("dials"))`). They run in order AFTER the lock is released, still on the same thread, before the method returns.
- `_save_session` captures `dict(self.session)` under the lock (a snapshot) and the write happens after release.
- Convert every under-lock bump/save to this. Keep the order of effects identical to today. Keep `self.lock` an RLock. Nested `_locked()` calls must defer to the outermost block's release; test this.
- Error handling: if a deferred effect raises, keep today's behavior (exceptions propagated to the same caller) and add one `record_activity(..., "error")` where today's code would have propagated from inside the lock.

## Tests
- A fake metrics store whose `bump` and `save_session` sleep 0.5 s and record order. During `_call_ended` on a background thread, `public_state()` on the main thread returns in under 0.1 s.
- Effect order recorded equals the order before the change. Capture it from today's code first, in a test against the pre-change commit.
- Nested `_locked()` test.
- The P2 call-flow test passes unchanged.

## Verify (PASS/FAIL each)
- [ ] Full suite passes.
- [ ] A grep shows no `_bump(`/`_save_session(` inside a `with self.lock:` block (paste it).
Commit `refactor(P19): defer storage I/O until the dialer lock is released`.
```

---

## P20: Guardrails and docs

**You check:** read `AGENTS.md`. It should tell a new person, or an AI, which folder to open for any change in under a minute.

```markdown
# P20: Lock in the structure: boundary checker, feature map, Cursor rules, README

Follow .cursor/rules/refactor-chain.mdc. No runtime changes.

## Build
1. `scripts/check_boundaries.py` (stdlib), run by `tests/test_boundaries.py`. It fails on:
   - Python: `shared/*` importing `features|web`; `features/<x>/*` importing `web` or `features.<y>.<module>` (only the package root `features.<y>` is allowed); `web/*` importing `features.<x>.<module>` other than `routes` and the package root.
   - JS: `static/core/**` importing `static/features/**`; a feature importing another feature's file other than `index.js`.
   - Any file over 600 lines (warning list), or over 900 (failure). Tests and docs are exempt.
   - Any class assembled from mixins defined in more than 2 files (Python: inspect each class's MRO source files; JS: mixin-factory chains), exempting stdlib/framework bases.
   - Leftover compatibility re-exports (modules whose body is only imports and `__all__`), other than package `__init__.py` files that define a feature's public API.
2. `AGENTS.md` at the repo root:
   - What the app is (2 lines). How to run: `python server.py`, the two ports, the tunnel to 8765.
   - **Feature map table**: feature | backend folder | frontend folder | entry points (routes, index.js) | tests | "to change X, open …" with 10 concrete rows (add a disposition, change what counts as a conversation, add a prospect column, add a dialer setting, add a Twilio webhook event, add a metric, change calling hours, add a CSV import heuristic, change the table UI, change sounds/effects).
   - Dependency rules (copied from the checker).
   - Vocabulary rule: statuses, dispositions, call states, metric keys and timezones are defined only in `shared/vocabulary.py` and `shared/time.py`; the browser gets them from the injected JSON; `schema.sql` is checked by a test.
   - How to run the tests and the two check scripts.
   - File size guideline: 200–600 lines, grouped by reason to change. Never split a file to hit a line count.
3. `.cursor/rules/architecture.mdc` (`alwaysApply: true`): a 15-line summary of AGENTS.md (feature folders, rules, where the vocabulary lives, run tests before finishing).
4. `README.md`: setup, `.env` keys, Twilio console setup (TwiML App Voice URL = `<PUBLIC_BASE_URL>/hooks/voice`, method POST; API key; a tunnel such as ngrok to port 8765), Supabase pointer to `docs/supabase/setup.md`, and the tests command.
5. Update `docs/supabase/setup.md` for anything that changed (anon key now required, migration script location).
6. Retire the chain:
   - Delete `.cursor/rules/refactor-chain.mdc`.
   - Keep `docs/refactor/` (LOG and plans) as history.
   - Add a final LOG entry summarizing before → after: file counts per feature, folders per feature, and the change-impact table re-measured. For each of the 10 AGENTS.md scenarios, count the files a change would need to open now.

## Verify (PASS/FAIL each)
- [ ] `python scripts/check_boundaries.py` passes with no failures (list the warnings).
- [ ] Full suite passes; `python scripts/check_static.py` OK.
- [ ] Report per feature: files, lines, folders (backend + frontend).
Commit `refactor(P20): guardrails, feature map, README`. Then tell the user the branch is ready to merge.
```

---

## If something goes wrong

- **A prompt reports FAIL or STOP:** don't continue. Paste the report into a new chat and ask for the smallest fix within that prompt's scope. If that fails, roll back with `git reset --hard HEAD~1`, then re-run the prompt.
- **The app breaks in a way the tests didn't catch:** that's a gap in the P2 net. Before fixing, ask for a characterization test that reproduces the break, then the fix.
- **You want to pause midway:** every commit leaves a working app. P7–P14 can run before any frontend prompt. P15–P18 depend only on P8 and P14.
