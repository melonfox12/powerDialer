# Cursor prompt: fix the critical issues from the architecture audit

Paste everything below the line into Cursor (Agent mode). It is self-contained.

---

You are fixing verified bugs in this repo (a Python power dialer: Twilio + Supabase/local JSON, vanilla JS in `/static`). This is a **bug-fix pass, not a refactor**. Follow `AGENTS.md`. Do not move or rename modules, do not restructure folders, do not touch `.env` or `crm_data/`.

## Ground rules

1. **Test first.** For every bug: write a failing test, show it fail, fix it, show it pass. Put tests in the existing files that match the area (`tests/test_settings.py`, `tests/test_metrics.py`, `tests/test_http.py`, `tests/test_call_flow.py`, or a new `tests/test_prospects.py` for store tests). Use the existing fakes and patterns (`tests/local_server.py`, `tests/test_transcript_storage/fixtures.py`).
2. **Run the full suite after every step:** `python -m unittest discover -s tests -t .` It must be green before you move on. Also run `python scripts/check_static.py` and `python -c "import server"`.
3. **One commit per step**, message `fix(<step>): <summary>`. Keep each diff small and limited to the files named.
4. Before deleting anything, grep `.py`, `.js`, `.html`, `.css`, tests and string literals for references, and list what you found in the commit message.
5. If a step turns out bigger than described, or the code doesn't match the description, **stop and report**. Don't improvise a redesign.
6. Don't change API payload key sets. `tests/test_http.py` locks `STATE_KEYS`, `LIVE_KEYS` and `SETTINGS_KEYS`. If a fix needs a key change, stop and ask.

## Step 0: make the suite green and remove traps

The suite currently fails 2 of 41 tests because commit `4607dfa` re-added files written against the deleted architecture.

- Delete `crm_store/leads/manual.py` (it imports deleted modules `crm_store.csv_io.fields` and `crm_store.statuses`) and the now-empty `crm_store/` tree.
- Delete `static/js/controllers/new-prospect.js` (it imports 6 missing modules and references 13 missing DOM ids; nothing imports it) and the empty `static/js/` tree.
- `tests/test_manual_prospect.py` imports `crm_store.CRMStore`. Port its 4 test cases to the live API (`features._prospects.csv_import.build_manual_lead` and `features.prospects.ProspectStore.add_lead`), keeping only the assertions that match current live behavior. If an assertion conflicts with live behavior (for example the speaker label `Prospect` vs `Agent`, or `review_count` taken from fields), **do not change live behavior**. Drop the assertion and list it in the commit message.
- Move `Claude outputs/example_leads.csv` to `tests/fixtures/example_leads.csv` and update `tests/test_transcript_storage/part_1.py:110`. Don't delete anything else in `Claude outputs/`.
- `tests/test_http.py:98-99` writes `docs/page-before.html` when it's missing. Make the test fail instead of writing a file.
- Delete `scripts/check_js_urls.py` (superseded by `check_static.py`, no references) and the unused `dumps_json` in `shared/_infra/files.py`.
- Repo hygiene:
  - `git rm -r --cached` every tracked `__pycache__/` and `*.pyc`, and `call_log.csv` (already in `.gitignore`, no code references it).
  - Delete the ghost directories that contain only `__pycache__`: `core/`, `routes/`, `supabase_store/`, `twilio_calls/`.
  - Add `.gitattributes` with `* text=auto eol=lf` (`*.bat` and `*.ps1` → `eol=crlf`, if any exist). Do **not** renormalize every file in this commit; just add the attribute file and note in the message that `git add --renormalize .` should be a separate commit.

Expected: 41/41 green (or the ported count).

## Step 1: stop sending Twilio secrets to the browser

- `features/settings.py:44-67` `settings_state` returns `auth_token` and `api_secret` in plaintext. Change it to return `""` for both (keep the keys so `SETTINGS_KEYS` is unchanged). `has_auth_token` and `has_api_secret` stay.
- `static/features/settings.js:9,11`: leave those inputs empty and show the placeholder "Saved — leave blank to keep" when the matching `has_*` flag is true.
- Saving with a blank secret already keeps the old value (`settings.py:93-96`). Add a test that proves it.
- Tests:
  - `GET /api/settings` never contains the stored token or secret.
  - A POST with a blank token keeps the stored one.

## Step 2: CSRF guard on the app server (local mode has no auth)

Today a cross-site `text/plain` POST to `/api/settings` rewrites the Twilio credentials and `PUBLIC_BASE_URL` (verified).

In `web.py`/`_web/respond.py`, for every state-changing request (POST and DELETE on the app server only, **not** the Twilio hook server):

- Reject with 403 when an `Origin` header is present and isn't `http://127.0.0.1:<APP_PORT>` or `http://localhost:<APP_PORT>`.
- Reject with 403 when the `Host` header isn't one of those hosts (this blocks DNS rebinding; apply it to GETs too).
- For JSON endpoints, reject with 415 unless `Content-Type` starts with `application/json`. `/api/import` must accept `application/octet-stream`, which is what `static/features/_prospects/csv.js:15-19` sends.
- `/api/debug` (`web.py:37-58`, sent with `keepalive` from `_core/api.js:25-30`) follows the same Origin and Host rules.

Tests, using `tests/local_server.py`:

- A `text/plain` POST is rejected.
- A foreign `Origin` is rejected.
- The same-origin JSON POST from the existing tests still passes.
- A CSV import still passes.

## Step 3: Supabase cache must not change before the write succeeds

`features/prospects.py:58-125` mutates the cached lead (`lead["status"] = status`, transcript and call-log appends) and then calls `backend.save_locked(lead)`. If the Supabase PATCH fails (`features/_prospects/backend_supabase.py:43-52`), the cache keeps the unsaved change. A failed "Do not call" then shows as saved, and after a restart the lead comes back as `new` and can be auto-dialed.

- Fix: build the updated lead as a copy, call `save_locked(copy)`, and only on success replace the cached entry. Apply this to `set_status`, `append_transcript` and `append_call_log`. Local backend behavior must stay the same.
- Also fix `backend_supabase.py:120-122`: `info["total"]` double-counts (`len(leads) + len(additions)` after `leads.extend(additions)`). It should be `len(leads)`, matching local.
- Tests:
  - A fake client whose PATCH raises `OSError` → `set_status` raises and `snapshot()` still shows the old status.
  - `add_csv` totals match between the local and Supabase-fake backends.

## Step 4: atomic metric increments

`features/metrics.py:110-121` does a GET of the value, then a POST of `current + amount`. Concurrent bumps lose counts (5 concurrent → stored 1).

- Add a SQL function to `docs/supabase/schema.sql`: `increment_metric(p_user_id uuid, p_day date, p_metric_key text, p_amount bigint)`. It upserts both `dialer_metric_daily` and `dialer_metric_totals` with `value = value + excluded.value`. It is `security definer` and executable by `service_role` only.
  - Use the existing metric-key list. `tests/test_vocabulary.py` counts the `metric_key in (...)` lists in `schema.sql`; update that expected count, or make the function reference the table checks instead of a new list.
- Call it once per bump with `client.request("POST", "rpc/increment_metric", payload=...)`. Remove `_increment`.
- Test: a fake client that records calls → one RPC per bump with the right payload.
- Add an "Upgrade" note to `docs/supabase/setup.md`: re-run `schema.sql`.

## Step 5: no network or disk I/O while holding the dialer lock

Metric bumps and `save_session` (Supabase HTTP, or a `metrics.json` write) run inside `with state.lock:`, which blocks webhooks and `/api/live` for that user. A slow store blocked `public_state()` for 1.4 s.

Call sites:

- `features/_dialer/calls.py:118-123` (`_new_call`, called inside the lock from `slots.py:12-29` and `queue.py:89`)
- `queue.py:86`
- `_call_events/pickup.py:20-23` and `:46-50`
- `_call_events/ended.py:37-43`
- `outcomes.py:31-33`
- `calls.py:77`

Fix pattern, keeping behavior identical otherwise: inside the lock, update in-memory counters and record intended effects (`bumps = [("dials", 1)]`, `save_session = True`). After the `with` block, execute them. Don't change what is counted or when, only where the I/O runs.

Test: a fake metrics store whose `bump` and `save_session` sleep 0.5 s → while `fill_slots` runs on another thread, `public_state()` returns in under 100 ms. Existing call-flow and session tests must stay green unchanged.

## Step 6: settings persistence and tenant leaks

- **Saved twice per POST:** `web.py:238-241` calls `session.save_settings(data)`, which already persists through `settings_saver` (`features/dialer.py:96-103`), and then calls `runtime.persist_settings(session)` again. Remove the second call. Test: one `dialer_settings` upsert per POST.
- **Signed-in users inherit the server's `.env` Twilio credentials:** `features/settings.py:40-41` merges `read_env(.env)` (which also falls back to `os.environ`, `shared/config.py:44-45`) under every account. For a signed-in account (`account_user_id` set), `values()` must not take `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_API_KEY`, `TWILIO_API_SECRET`, `TWILIO_TWIML_APP_SID` or `PUBLIC_BASE_URL` from `.env` or the environment. Preference defaults may still come from `.env`.
  - Thread this through without `getattr`: pass an explicit `signed_in: bool` to `values()` from its callers (`twilio_api.py:81,108`, `queue.py:35`, `projection.py:65`, `settings.py`, `accounts.py:102`).
  - Test: `.env` holds Twilio keys, and a signed-in `Dialer`'s `settings_state()` shows empty SID and token.
- **Supabase configured without an anon key** makes every `/api/*` call return 401 while the UI shows no sign-in (`features/accounts.py:39,122-124`). Make `AppRuntime.configure()` raise a clear `ValueError` at startup: "SUPABASE_ANON_KEY is required when Supabase storage is configured". Test it.
- **The migration script writes prospects with no `user_id`** (`scripts/migrate_to_supabase.py`), so no signed-in user can see them. Add a required `--user-id` argument and set `user_id` on every row it writes.

## Step 7: debug-log redaction

`shared/_infra/files.py:12-14` misses `TWILIO_AUTH_TOKEN=…` and `TWILIO_API_SECRET=…` (no word boundary after `_`), and for `Authorization: Bearer <jwt>` it redacts the word "Bearer" but leaves the token.

Fix the regex. Unit-test these inputs, all fully redacted:

- `TWILIO_AUTH_TOKEN=abc`
- `TWILIO_API_SECRET=zz`
- `auth_token: abc`
- `Authorization: Bearer eyJabc`
- `sb_secret_xxx`

## Not in this pass (needs a product decision, so don't do it)

- **Calling hours** are stored and validated but not enforced (`within_calling_window` in `features/_dialer/session_stats.py:105` is never called; enforcement was removed in commit `70366cb`). **Leave this alone** unless I add a section here telling you how unknown-timezone leads should be handled.
- No refactors: no facade removal, no merging files, no CSS changes.

## Final report

When you're done, reply with:

1. Each step: commit hash, files changed, tests added.
2. Full suite output (count and status).
3. Anything you stopped on or dropped, and why.
