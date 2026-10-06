# Architecture map

Phase 1 plan for the feature-slice refactor. Runtime behavior stays the same.
The only sanctioned rewrite is mixin composition: `self.x` becomes `state.x`, and
`self.method()` becomes a function that receives `state` and its collaborators.
Method bodies stay verbatim. No bug fixes (see "Noticed, not fixed").

Baseline at this commit: 163 files, 52 directories (excluding `.git`, `.venv`,
`__pycache__`, `Claude outputs`, and `.env`). Largest text file is
`static/css/linear/metrics.css` at 174 lines. Full suite: 37 tests, OK.

## Stop — contradictions the later phases cannot all satisfy

These are real conflicts in the execution prompt. This plan does not invent a
silent workaround. Replying `go` accepts the allowlist in this section. If that
allowlist is wrong, say so before phase 2; phase 2 will freeze `GET /` and the
allowlist becomes the phase 6 assertion.

`docs/page-before.html` is captured in phase 2 from today's `GET /`. Phase 6
then requires that response to match after normalizing line endings, with the
only stated exception being a reorder of top-level `<dialog>` elements. Three
later steps change that response body:

1. Phase 3 deletes proven-dead markup, including `#enterLiveButton` in
   `static/app-shell/dialer.html` (required dead-code list).
2. Phase 4 injects vocabulary JSON into the page (required).
3. Phase 6 moves CSS and JS, so `<link href>` and `<script src>` in
   `static/app-shell/chrome.html` cannot stay byte-identical, and
   `static/css/` is deleted (required). Keeping the old URLs as shims is
   forbidden ("no compatibility shims survive the phase that creates them").

`GET /` therefore cannot be byte-identical to `docs/page-before.html` under the
rules as written.

Allowlist the phase 6 test will use (this is the deviation):

- Normalize CR/LF, then compare.
- Top-level `<dialog>` elements may be reordered. Nothing else in the body may
  move.
- `#enterLiveButton` (and only that dead node) may be absent.
- Exactly one `<script type="application/json" id="vocabulary">` may be present.
- `<link rel="stylesheet">` hrefs and the module `<script src>` may differ.
  Cascade order of the CSS those links load must still make the same
  declarations win. Playwright (or the fallback in phase 6) is the visual check.
- Static `<option>` lists in the prospects filter stay in the HTML so the rest
  of the markup matches. They are a residual vocabulary copy, locked by a test
  that their values and labels equal `shared/vocabulary.py`. Generating those
  options from JSON would delete markup and fail even this allowlist.

`StatusCallbackEvent` value `"answered"` in `twilio_calls/client/calls.py` is
Twilio's callback-event subscription. It is not the dead `CallStatus ==
"answered"` branch. Phase 3 must not delete that parameter.

## Deviations from the target map

Each one is a split, a placement, or a type choice the line rules or the
verbatim-body rule force.

1. `shared/infra.py` is over ~250 lines once the REST client (138), pool (39),
   debug log (42), and atomic JSON helpers are together. Public surface stays
   `shared/infra.py`. Bodies move to `shared/_infra/supabase.py` and
   `shared/_infra/files.py`.
2. `Call` stays a dict. `_new_call` builds a dict and every method uses
   `call["field"]`. A dataclass would rewrite those bodies, which the
   composition rule does not allow. `features/_dialer/state.py` documents the
   dict shape next to `DialerState`. `DialerState` is the object that replaces
   `self`.
3. `features/_dialer/call_events.py` would be ~330 lines after dead-code
   removal (dispatch + pickup + end + transcript), and phase 7 fails any file
   over 400. Split on the seams the target map already names:
   `call_events.py` dispatches; `features/_dialer/_call_events/pickup.py`,
   `transcript.py`, and `ended.py` hold the handlers.
4. Queue timing calls `fill_slots`. If both lived in `queue.py` the file is
   ~270 lines and the recursive split rule applies. `fill_slots` cannot live
   in the parent while timers import the parent (cycle). So
   `features/_dialer/_queue/slots.py` owns `fill_slots`,
   `features/_dialer/_queue/timing.py` owns advance and calling-window timers
   and imports slots, and `features/_dialer/queue.py` owns manual dial and
   `start` and imports both. Neither child imports `queue.py`.
5. `features/metrics.py` is estimated at ~230 lines (local store 80 + Supabase
   store 128 + route). It stays one file. Split into `features/_metrics/` only
   if the moved file crosses ~250.
6. `features/settings.py` is estimated at ~200 lines and stays one file.
7. Frontend features do not import each other. The backend feature order allows
   an entry to import entries to its left; the frontend chain does not. Shared
   notifications go through the core registry (`registerRenderer`,
   `registerTab`, plus a preference hook so settings can update arcade without
   importing it).
8. The caller-pool panel is a dialer surface (timezone filter calls
   `set_timezone_filter`) but its markup sits inside today's `metrics.html`,
   after the prospects panel. It becomes `static/features/_dialer/pool.html`,
   concatenated at that same position. It is not a seventh feature.
9. The login gate stays the first node in `static/shell.html`. It is not a
   `<dialog>`, so moving it into `auth.html` would change `GET /` beyond the
   allowlist. `static/features/auth.js` binds it.
10. `dialer.py` (8 lines, calls `server.serve`) stays. The target map does not
    name it; deleting it would drop a working launcher. It imports only
    `server`.
11. `scripts/check_js_urls.py` is replaced by `scripts/check_static.py` in
    phase 2 and deleted in phase 7 once the new script covers import crawling.
    It is not a shim; nothing imports it.
12. Supabase client tests move to `tests/test_accounts.py` because there is no
    `test_shared.py` in the target list. Accounts is the feature that chooses
    the backend and checks the Google token. The settings round-trip test in
    that module moves to `tests/test_settings.py`. Assertions stay.
13. Arcade's mixin tower (`ParticlesMixin(ReelsMixin(AudioMixin(PlaybackMixin(ArcadeCore))))`)
    is the same composition rewrite as `TwilioDialer`: one state object in
    `static/features/arcade.js`, parts in `static/features/_arcade/`.
14. Setting default values live in `shared/vocabulary.py` as `SETTING_DEFAULTS`.
    `shared/config.py` `write_env` resets blank preferences from that dict. If
    the values lived in `features/settings.py`, config would import a feature
    and the dependency chain would point the wrong way. `twilio_calls/settings/defaults.py`
    aliases `DIALER_DEFAULTS = SETTING_DEFAULTS` until phase 5 deletes the
    alias. Validation (`_preferences`) stays with settings. Secret form fields
    are `SECRET_INPUTS` (DOM id + label), not env keys.

## (b) Target tree and estimated lines

Estimates are current line counts minus dead code, plus a thin route wrapper.
They are ceilings, not targets. A file under ~40 lines is not created unless it
is a public entry or a named part that is already a natural seam above that floor.

```
server.py                         ~45   wires features into web, starts both servers
dialer.py                         ~8    launcher, unchanged role
web.py                            ~160  parse, static, page assembly, route dispatch, error profiles
_web/hooks.py                     ~90   Twilio webhook server + signature check

shared/vocabulary.py              ~140  the definitions (see section e)
shared/config.py                  ~90   paths, ports, read_env, write_env
shared/infra.py                   ~50   public re-exports: client, debug_event, atomic JSON, utc_now
shared/_infra/supabase.py         ~190  SupabaseClient, pool, key checks
shared/_infra/files.py            ~80   debug log + atomic JSON read/write

features/settings.py              ~200  defaults, validation, settings view, env + Supabase persistence, ROUTES
features/metrics.py               ~230  local + Supabase metrics, ROUTES
features/prospects.py             ~220  ProspectStore rules + ROUTES
features/_prospects/csv_import.py ~210  parse + header heuristics + manual-lead build
features/_prospects/csv_export.py ~40   csv_bytes_for (public seam; ~30 lines of logic today)
features/_prospects/backend_local.py      ~140  JSON parts + load/save/snapshot, no rules
features/_prospects/backend_supabase.py   ~160  REST fetch/write/delete, no rules

features/dialer.py                ~180  public methods routes call, ROUTES, part import order
features/_dialer/state.py         ~120  DialerState + documented Call dict
features/_dialer/session_stats.py ~120  stage, session accounting, local time, calling window
features/_dialer/twilio_api.py    ~200  REST, TwiML helpers, token, signature; no dialer state
features/_dialer/queue.py         ~180  start, manual dial
features/_dialer/_queue/slots.py  ~80   fill_slots
features/_dialer/_queue/timing.py ~70   advance + calling-window timers
features/_dialer/call_events.py   ~120  webhook + client-voice dispatch
features/_dialer/_call_events/pickup.py     ~70
features/_dialer/_call_events/transcript.py ~90
features/_dialer/_call_events/ended.py      ~90
features/_dialer/outcomes.py      ~70
features/_dialer/projection.py    ~110  public_state, live_state

features/accounts.py              ~180  backend choice, sessions, Google token check, health, ROUTES

static/main.js                    ~50   boots features in today's order
static/core.js                    ~80   registries + navigation orchestration
static/_core/api.js               ~85
static/_core/store.js             ~70   only keys read by 2+ features
static/_core/dom.js               ~60   byId, setText, initials, toast, phone, dates
static/_core/time.js              ~50   timezone conversion (vocabulary zones come from JSON)
static/shell.html                 ~60   skeleton; login gate stays here
static/base.css                   ~shared tokens, layout, shell, responsive rules that are not feature-owned

static/features/dialer.js         ~200  bind, poll refresh of dialer state, keyboard, outcomes
static/features/dialer.html       today's dialer.html minus the dead button
static/features/dialer.css
static/features/_dialer/pool.html the pool panel, concatenated where metrics.html has it now
static/features/_dialer/voice.js  ~150  device connect + bind
static/features/_dialer/_voice/devices.js  ~113
static/features/_dialer/_voice/testing.js  ~133
static/features/_dialer/stage.js  ~180  call stage, timer, waveform, card
static/features/_dialer/session_ui.js ~160  controls, queue strip, outcome row, session goal, monitor
static/features/prospects.js      ~160
static/features/prospects.html    prospects panel from metrics.html
static/features/prospects.css
static/features/_prospects/table.js       ~200
static/features/_prospects/csv.js         ~190  import, export button, add-prospect dialog logic
static/features/_prospects/transcript.js  ~70
static/features/performance.js    ~200  metrics render + charts
static/features/performance.html
static/features/performance.css
static/features/settings.js       ~180
static/features/settings.html     settings dialog
static/features/settings.css
static/features/auth.js           ~90
static/features/auth.css          login-gate rules only; markup stays in shell.html
static/features/arcade.js         ~150  state + boot; no mixin tower
static/features/arcade.html       arcade nodes if they are top-level; else the nodes stay in the partial that holds them today
static/features/arcade.css
static/features/_arcade/shell.js
static/features/_arcade/playback.js
static/features/_arcade/audio.js
static/features/_arcade/reels.js
static/features/_arcade/particles.js

scripts/check_architecture.py
scripts/check_static.py
scripts/migrate_to_supabase.py    absorbs migrate_local_data

tests/test_settings.py
tests/test_metrics.py
tests/test_prospects.py
tests/test_dialer.py
tests/test_accounts.py
tests/test_http.py
tests/test_call_flow.py
tests/test_static.py
tests/test_architecture.py

docs/page-before.html             phase 2 snapshot
docs/supabase/schema.sql          stays; metric-key lists locked to vocabulary by a test
docs/supabase/setup.md            stays
docs/linear-design-system/        stays; reference only, not moved
```

Page assembly order in `web.py` (this order is what keeps non-dialog markup put):

1. `static/shell.html` (today's `chrome.html`)
2. `static/features/dialer.html`
3. `static/features/performance.html`
4. `static/features/prospects.html`
5. `static/features/_dialer/pool.html`
6. Top-level dialogs from `settings.html`, dialer session-summary (inside `dialer.html` or a dialog partial), and the add-prospect dialog from prospects. Dialogs may be reordered. Their internal markup may not change.

`_prospects` import order, written at the top of `features/prospects.py`:

`csv_import → csv_export → backend_local → backend_supabase`

No child imports `prospects.py`. Backends do not import each other. CSV modules do not import backends.

`_dialer` import order, written at the top of `features/dialer.py`:

`twilio_api → state → session_stats → queue (which imports _queue/slots then _queue/timing) → call_events (which imports _call_events/pickup, transcript, ended) → outcomes → projection`

`_queue/timing.py` may import `_queue/slots.py`. `_call_events/*` may import `twilio_api` and `state` only, not `call_events.py` and not each other unless a later read shows a one-way call. `outcomes` may import `queue` timers. `projection` may import `session_stats` and `state`. Nothing imports `dialer.py`.

`_core` import order, written at the top of `static/core.js`:

`api → store → dom → time`

Registry functions live in `core.js` so features never import a sibling that imports features.

Frontend boot order in `static/main.js` stays today's order: debug listeners, arcade, navigation, dialogs, prospects, add-prospect, prospect menu, settings, csv, search and status filter, call monitor, session goal, dialer, keyboard, outcomes, arcade preference inputs, voice, auth, `initAuth`, polling.

## (c) Dependency graph

Acyclic. An edge means "imports".

```
server.py
  → web.py
  → features/accounts.py
  → features/dialer.py
  → features/prospects.py
  → features/metrics.py
  → features/settings.py

web.py
  → features/{settings,metrics,prospects,dialer,accounts}.py   (ROUTES only)
  → shared/{config,vocabulary,infra}.py
  → _web/hooks.py
  → stdlib http.server

_web/hooks.py
  → shared/infra.py          (debug log)
  → features/accounts.py     (token lookup / local dialer)
  → features/dialer.py       (validate_webhook, handle_webhook, handle_client_voice)

features/settings.py    → shared only
features/metrics.py     → shared only
features/prospects.py   → shared only
features/dialer.py      → features/settings.py, features/metrics.py, features/prospects.py, shared
features/accounts.py    → features/settings.py, features/metrics.py, features/prospects.py, features/dialer.py, shared

shared/*                → stdlib only
features/_<name>/*      → shared, and earlier parts in the order above
                          never the feature entry, never another feature's _<x>/
```

Feature order (a feature entry may import only entries to its left):

```
settings → metrics → prospects → dialer → accounts
```

Frontend:

```
static/main.js → static/features/*.js → static/core.js → static/_core/* → browser APIs
```

No feature JS file imports another feature. No `shared` or `core` import reaches `web` or a feature.

`scripts/migrate_to_supabase.py` imports `features/prospects.py` (the moved `migrate_local_data`) and `shared`. Scripts are not on the runtime chain. `check_architecture.py` treats `scripts/` as allowed to import feature entries, and forbids scripts from importing `_<feature>/`.

## (d) TwilioDialer state

Every `self.<attr>` found on the mixin classes that build `TwilioDialer` moves onto `DialerState` in `features/_dialer/state.py`. `TokenIndex._lock` and `TokenIndex._tokens` stay on `TokenIndex` inside `twilio_api.py`; accounts holds the index, and `state.token_index` points at it.

`crm`, `metrics`, `env_path`, `token_index`, and `settings_saver` stay fields on `DialerState` so call sites change from `self.crm` to `state.crm` and nothing else. They are collaborators only in the sense that accounts constructs them and passes them into `DialerState`.

| Attribute | Written by (today's method) | Read by |
| --- | --- | --- |
| `crm` | `CoreMixin.__init__` | `_pool_leads`, `set_timezone_filter`, `public_state`, `skip_active`, `choose_outcome`, `update_status`, `_dialable_lead`, `fill_slots`, `_call_ended`, `_transcription_event` |
| `env_path` | `__init__` | `_values`, `save_settings` |
| `metrics` | `__init__` | `_save_session`, `_bump`, `stop` |
| `storage_name` | `__init__`, `AppRuntime.configure`, `session_for` | `settings_state` |
| `account_values` | `__init__`, `reload_settings` | `_values`, `save_settings` |
| `account_user_id` | `__init__`, `session_for` | `save_settings`, `persist_settings`, `reload_settings` |
| `account_email` | `__init__`, `session_for` | `GET /api/auth/me` |
| `token_index` | `__init__`, `configure`, `session_for` | `_watch_token`, `_release_tokens` |
| `settings_saver` | `session_for` (not in `__init__`) | `save_settings` |
| `lock` | `__init__` | almost every mutator |
| `running` | `__init__`, `start`, `stop`, `_create_call` | stage projection, queue, controls, webhooks |
| `paused` | `__init__`, `start`, `pause`, `stop`, `_pin_manual_dial`, `_create_call`, `_agent_call_ended` | stage, queue, controls |
| `agent_ready` | `__init__`, `start`, `stop`, `handle_client_voice`, `handle_webhook`, `_agent_call_ended` | `fill_slots`, `public_state`, `pause` |
| `agent_call_uuid` | `__init__`, `_create_call`, `handle_webhook`, `handle_client_voice` | webhook dispatch |
| `agent_call_token` | `__init__`, `start` | voice token watch |
| `conference` | `__init__`, `start` | TwiML, `handle_client_voice`, `_live_twiml` |
| `callers` | `__init__`, `start` | `_next_caller`, `public_state` |
| `caller_index` | `__init__`, `start`, `_next_caller` | `_next_caller` |
| `active` | `__init__`, `start`, `stop`, `skip_active`, `_pickup`, `_select_human`, `_call_ended` | stage, outcomes, controls, projection |
| `pending_outcome` | `__init__`, `start`, `stop`, `hangup_active`, `skip_active`, `choose_outcome`, `_call_ended` | stage, queue, outcomes |
| `calls` | `__init__` (dict), `_new_call` inserts | webhook lookup, `_release_tokens`, `stop`, `handle_client_voice` |
| `in_flight` | `__init__`, `_new_call`, `_cancel_call`, `_create_call` | stage, controls, `fill_slots`, projection |
| `last_error` | `__init__`, `start`, `_create_call`, `_transfer` (dead) | `public_state` |
| `last_event` | `__init__` ("Ready"); then `set_timezone_filter`, `_create_call`, `pause`, `hangup_active`, `skip_active`, `stop`, `_pin_manual_dial`, `start`, `handle_client_voice`, `handle_webhook`, `_call_ended`, `_agent_call_ended`, `_select_human` (dead), `_pickup`, `_machine_result`, `choose_outcome` | `public_state` |
| `public_base_url` | `__init__`, `start` | `_url`, hook signature URL |
| `settings` | `__init__`, `start`, `save_settings` | Twilio requests, timers, `_values` consumers |
| `selected_timezone` | `__init__`, `set_timezone_filter` | `_pool_leads`, `start`, `public_state` |
| `activity_log` | `__init__`, `start` clears | `record_activity`, `public_state` |
| `activity_sequence` | `__init__`, `start`, `record_activity` | `record_activity` |
| `session` | `__init__`, `start`, `stop` | session stats, `_bump` dials, outcomes |
| `advance_timer` | `__init__`, pause/stop/start/pin/schedule/advance | queue timing |
| `advance_at` | same group | `public_state`, schedule |
| `advance_remaining` | same group | pause/resume |
| `queue_total` | `__init__`, `set_timezone_filter`, `start` | `public_state` |
| `calling_window_timer` | `__init__`, schedule/check, pause, stop | queue timing |
| `manual_lead_id` | `__init__`, `start`, `stop`, `_claim_manual_lead`, `_pin_manual_dial` | `fill_slots`, `public_state` |

Call dict keys (stay dict keys, owned by the call object inside `state.calls` / `state.in_flight`): `token`, `kind`, `lead_id`, `lead`, `call_uuid`, `state`, `handled`, `cancelled`, `machine`, `transcribing`, `transcript_partials`, `transcription_started`, `caller_id`, `answered_by`, `picked_up`, `connect_counted`, `transcript_lines`, `end_processed`, plus `outcome_chosen` and `wrapping` set later by outcome and end handlers. `answer_detection_timer` is deleted in phase 3 (only ever set to `None`).

`last_event` writers today, by file (10 files, matching the audit's "about 11"): `dialer/core.py`, `client/calls.py`, `lifecycle/controls.py`, `lifecycle/queue/manual.py`, `token/start.py`, `token/voice.py`, `transcript/ended.py`, `webhooks/dispatch.py`, `webhooks/live.py` (dead path), `webhooks/pickup.py`.

## (e) Vocabulary, and the single home for each copy

Home: `shared/vocabulary.py`. The browser receives `json.dumps` of the public dict injected as `<script type="application/json" id="vocabulary">`. JS reads it through `static/core.js`. Python features import the names. `docs/supabase/schema.sql` keeps its SQL lists; a test asserts those lists equal `METRIC_KEYS`.

| Concept | Single home | Copies replaced |
| --- | --- | --- |
| Statuses `(key, label, tone)` | `STATUSES` | `crm_store/statuses.py` `STATUSES` tuple (keys only). `static/js/utils/format.js` `STATUS_STYLES` / `STATUS_LABELS` / `STATUS_COLOR_VARS`. Hardcoded key lists in `static/js/views/metrics/charts.js`, `static/js/views/prospects-table/rows.js`, `static/js/controllers/add-prospect.js`. Option labels in `static/app-shell/metrics.html` stay as markup and are tested against this table (see the allowlist). Tone fields are `label`, `color` (`--muted`, `--amber`, `--red`, `--success`), `className` (`neutral`, `callback`, `negative`, `positive`). |
| Dispositions | `DISPOSITIONS` + `DISPOSITION_TO_STATUS` | `core/dialer_session.py` `DISPOSITION_TO_STATUS`. Button wiring in `static/js/controllers/outcomes.js` (`booked`, `not_interested`, `no_answer`, `do_not_call`, `callback`). |
| Outcome → metric | `OUTCOME_METRIC` | `twilio_calls/lifecycle/outcome.py` dict `call→call_later`, `interested→interested`, `booked→booked`, default `disqualified`. `skip_active` bumps `call_later` and must use the same map. |
| Metric keys | `METRIC_KEYS` | `supabase_store/client/keys.py` `METRIC_KEYS`. Five copies in `docs/supabase/schema.sql` (checked, not generated). Snapshot shapes in both metrics stores keep reading these keys. |
| Dialer stages | `STAGES` | `core/dialer_session.py` `STAGES`. JS stage strings in `static/js/views/dialer/call-stage/stage.js` stay display copy but the allowed set is this tuple: `idle`, `dialing`, `ringing`, `connected`, `wrapup`, `paused`. |
| Call states | `CALL_STATES` | Produced today: `creating`, `calling agent`, `ringing`, `live`, `cancelled`, `ended`, `skipped`. `listening` and `connecting` are not in the tuple; phase 3 deletes the checks that mention them. |
| Timezone names | `TIMEZONE_NAMES` | `core/dialer_session.py` `TIMEZONE_NAMES`. `static/js/utils/time.js` `timezoneFor` map. |
| Timezone aliases | `TIMEZONE_ALIASES`, `UTC_OFFSET_ZONES` | `crm_store/statuses.py`. Used by CSV import. |
| Setting keys | `SETTING_KEYS`, `SETTING_DEFAULTS`, `SECRET_INPUTS` | `DIALER_DEFAULTS` in `twilio_calls/settings/defaults.py` (values live here so `write_env` does not import settings; validation stays in settings). `REMOTE_SETTING_KEYS` in `supabase_store/client/keys.py`. `SECRET_FIELDS` in `static/js/controllers/settings.js`. |
| `SETTINGS_ROW_ID = "app"` | `shared/vocabulary.py` | `supabase_store/client/keys.py`. It is the legacy row id, not a user id. |

CSV header heuristics (`PHONE_HEADER_WORDS`, `BUSINESS_HEADER_WORDS`, `TIMEZONE_HEADER_WORDS`, `REVIEW_HEADER_WORDS`, `JUNK_HEADER`, `SCIENTIFIC_NUMBER`, `TIMEZONE_ABBREVIATION`) are import behavior, not shared vocabulary. They move only to `features/_prospects/csv_import.py`.

Phase 4 breaks the storage→dialer import: `supabase_store/client/keys.py` currently imports `twilio_calls.settings.DIALER_DEFAULTS`. After phase 4 that module imports `METRIC_KEYS`, `REMOTE_SETTING_KEYS`, and `SETTINGS_ROW_ID` from `shared.vocabulary` and does not import `twilio_calls`. Default values live in `SETTING_DEFAULTS` (deviation 14). Phase 5 deletes the `DIALER_DEFAULTS` alias; it does not move the values back into settings.

## (a) Current file → target

Barrel files (`__init__.py` that only re-export, and JS files that only re-export) are deleted when their package is emptied. They are not shims.

### Root and servers

| Current | Symbols | Target |
| --- | --- | --- |
| `server.py` | `QuietThreadingHTTPServer`, `serve` | `server.py`. `configure(migrate=True)` becomes `configure()` in phase 3. |
| `dialer.py` | (no defs; calls `serve`) | stays |
| `routes/__init__.py` | none | deleted when `routes/` is empty (phase 5, with `web.py`) |
| `routes/http.py` | `log_server_fault`, `HandlerMixin.begin_trace`, `finish_trace`, `read_body`, `read_json`, `send_app_page`, `send_file`, `send_json`, `send_bytes`, `log_error`, `log_message`, `serve_static` | `web.py`. Page assembly learns the partial order and the vocabulary script. |
| `routes/hooks.py` | `make_hook_handler`, nested `HookHandler.do_GET`, `do_POST`, `resolve_dialer`, `dispatch`, `log_error`, `log_message` | `_web/hooks.py` |
| `routes/ui/__init__.py` | `make_app_handler` | `web.py` route-table dispatch. The mixin class `AppHandler` is deleted as a composition. |
| `routes/ui/read.py` | `ReadMixin.do_GET` | split by path into feature `ROUTES` (table below) |
| `routes/ui/write.py` | `WriteMixin.do_POST`, `do_DELETE` | split into feature `ROUTES`. `/api/enter-live` deleted in phase 3. |
| `routes/ui/account.py` | `AccountMixin.open_account`, `ingest_client_debug`, `report_storage_error` | `open_account` → `features/accounts.py`. `ingest_client_debug` → `web.py` (it is HTTP glue, path `/api/debug`, and it does not belong to a feature). `report_storage_error` → `web.py` error profile `GET reads`. |
| `routes/runtime.py` | `Account`, `Account.__init__`, `AppRuntime.__init__`, `configure`, `_ping`, `health`, `session_for`, `persist_settings`, `reload_settings`. Constants `APP_DIR`, `STATIC_DIR`, `CRM_PATH`, `METRICS_PATH`, `ENV_PATH`, `APP_HOST`, `APP_PORT`, `HOOK_HOST`, `HOOK_PORT`, `MAX_BODY`, `PUBLIC_API_PATHS`, `QUIET_HTTP` | `Account`, `configure`, `_ping`, `health`, `session_for` → `features/accounts.py`. `persist_settings`, `reload_settings` → `features/settings.py`. Paths, ports, `MAX_BODY`, `QUIET_HTTP`, `PUBLIC_API_PATHS` → `shared/config.py`. `migrate` parameter deleted in phase 3 (body never reads it). |

Route table (`method`, path, owner, error profile):

| Method | Path | Owner | Profile |
| --- | --- | --- | --- |
| GET | `/`, `/index.html`, `/static/`, `/static/index.html` | `web.py` page assembly | file 404 JSON, not a named profile |
| GET | static files | `web.py` | same |
| POST | `/api/debug` | `web.py` | its own 413/400/204, unchanged |
| GET | `/api/auth/config` | accounts | none (always 200) |
| GET | `/api/health` | accounts | none (200 or 503 from payload) |
| GET | `/api/auth/me` | accounts | 401 before the handler, as today |
| GET | `/api/settings` | settings | none |
| POST | `/api/settings` | settings | POST |
| GET | `/api/metrics` | metrics | GET reads |
| POST | `/api/leads` | prospects | POST |
| POST | `/api/import` | prospects | POST |
| GET | `/api/export.csv` | prospects | GET reads |
| DELETE | `/api/leads/{id}` | prospects | DELETE |
| POST | `/api/leads/{id}/status` | dialer (`update_status`) | POST |
| POST | `/api/timezone` | dialer | POST |
| POST | `/api/start` | dialer | POST |
| POST | `/api/pause` | dialer | POST |
| POST | `/api/stop` | dialer | POST |
| POST | `/api/hangup` | dialer | POST |
| POST | `/api/skip` | dialer | POST |
| POST | `/api/advance` | dialer | POST |
| POST | `/api/leads/{id}/dial` | dialer | POST |
| GET | `/api/state` | dialer | GET reads |
| GET | `/api/live` | dialer | GET reads |
| GET | `/api/voice-token` | dialer | voice-token |
| POST | `/api/enter-live` | deleted (dead) | — |
| POST/GET | `/hooks/voice`, `/hooks/{token}/{action}` | `_web/hooks.py` | unchanged 403/404/413/500 |

POST profile: `ValueError` / `KeyError` / `UnicodeDecodeError` → 400, `OSError` → 500, other → 502. GET reads: `OSError` → 502. DELETE: `KeyError` → 404, `OSError` → 500. voice-token: `ValueError` → 400. Hook errors stay as they are in `routes/hooks.py` (not these profiles).

### shared sources today

| Current | Symbols | Target |
| --- | --- | --- |
| `core/__init__.py` | none | deleted with `core/` |
| `core/debug_log.py` | `enable`, `debug_event`, `_redact` | `shared/_infra/files.py`, exported from `shared/infra.py` |
| `core/dialer_session.py` | `STAGES`, `DISPOSITION_TO_STATUS`, `TIMEZONE_NAMES` | `shared/vocabulary.py` |
| | `dialer_stage`, `status_for_disposition`, `new_session`, `add_connect`, `record_conversation`, `record_disposition`, `recent_streak`, `local_time`, `within_calling_window`, `session_summary` | `features/_dialer/session_stats.py`. `status_for_disposition` reads vocabulary. |
| `core/metrics_store.py` | `MetricsStore.__init__`, `load`, `save`, `_today`, `bump`, `save_session`, `recent_sessions`, `snapshot` | `features/metrics.py` |
| `crm_store/__init__.py` | re-exports | deleted with the package |
| `crm_store/statuses.py` | `STATUSES`, `TIMEZONE_ALIASES`, `UTC_OFFSET_ZONES` | `shared/vocabulary.py` |
| | `PHONE_HEADER_WORDS`, `BUSINESS_HEADER_WORDS`, `TIMEZONE_HEADER_WORDS`, `REVIEW_HEADER_WORDS`, `TIMEZONE_ABBREVIATION`, `JUNK_HEADER`, `SCIENTIFIC_NUMBER` | `features/_prospects/csv_import.py` |
| | `utc_now` | `shared/infra.py` |
| `crm_store/csv_io/__init__.py` | re-exports | deleted |
| `crm_store/csv_io/export.py` | `csv_bytes_for` | `features/_prospects/csv_export.py` |
| `crm_store/csv_io/fields.py` | `_phone`, `_timezone`, `_review_count`, `_choose_dialect`, `_read_csv`, `_unique_headers` | `features/_prospects/csv_import.py` (export uses `_phone` too; if export is the only caller of a helper, that helper stays in `csv_export.py`) |
| `crm_store/csv_io/parse.py` | `parse_csv` | `features/_prospects/csv_import.py` |
| `crm_store/leads/__init__.py` | `CRMStore` | `features/prospects.py` `ProspectStore` |
| `crm_store/leads/manual.py` | `build_manual_lead`, `_text`, `_extra_fields`, `_transcript` | `features/_prospects/csv_import.py` |
| `crm_store/leads/parts.py` | `json_line_count`, `lead_chunks`, `read_lead_parts`, `write_lead_parts` | `features/_prospects/backend_local.py`. Atomic replace helper, if extracted verbatim, also used by metrics via `shared/_infra/files.py`. |
| `crm_store/leads/records.py` | `RecordMixin.add_lead`, `add_csv`, `set_status`, `append_transcript`, `append_call_log`, `remove` | rules → `features/prospects.py` (one copy). Persistence calls → `backend_local.py`. |
| `crm_store/leads/storage.py` | `StorageMixin.__init__`, `_stores_parts`, `load`, `save`, `expire_due`, `snapshot`, `timezone_groups`, `csv_bytes` | load/save/parts → `backend_local.py`. `expire_due` rule → `prospects.py`. `snapshot`, `timezone_groups`, `csv_bytes` orchestration → `prospects.py`. |
| `supabase_store/__init__.py` | re-exports including `hydrate_env_from_supabase` | deleted. The hydrate name is dead (phase 3). |
| `supabase_store/client/__init__.py` | re-exports | deleted |
| `supabase_store/client/keys.py` | `METRIC_KEYS`, `REMOTE_SETTING_KEYS`, `SETTINGS_ROW_ID` | `shared/vocabulary.py`. File deleted. This is the module that imports `twilio_calls`. |
| `supabase_store/client/pool.py` | `_ConnectionPool.__init__`, `_new`, `send` | `shared/_infra/supabase.py` |
| `supabase_store/client/session.py` | `SupabaseClient.__init__`, `from_env`, `auth_user`, `_fetch_auth_user`, `request`, `select_all` | `shared/_infra/supabase.py` |
| `supabase_store/leads/__init__.py` | `SupabaseCRMStore` | `features/prospects.py` (one store, two backends) |
| `supabase_store/leads/changes.py` | `ChangeMixin.add_lead`, `add_csv`, `set_status`, `remove` | rules (`set_status` body) → `prospects.py`, one copy shared with local. POST/DELETE mechanics → `backend_supabase.py`. |
| `supabase_store/leads/records.py` | `RecordMixin.__init__`, `_scope`, `_touch`, `_fetch`, `_all`, `_write`, `_expire`, `snapshot`, `timezone_groups`, `csv_bytes` | persistence → `backend_supabase.py`. `snapshot` / `timezone_groups` / `csv_bytes` orchestration → `prospects.py`. |
| `supabase_store/leads/metrics.py` | `SupabaseMetricsStore.__init__`, `_scope`, `bump`, `_increment`, `save_session`, `recent_sessions`, `snapshot`, `_load_snapshot` | `features/metrics.py` |
| `supabase_store/transcripts/__init__.py` | re-exports | deleted |
| `supabase_store/transcripts/mixin.py` | `TranscriptMixin.append_transcript`, `append_call_log` | rules → `prospects.py` (duplicate of `crm_store/leads/records.py`). Write → `backend_supabase.py`. |
| `supabase_store/transcripts/settings_io.py` | `load_app_settings`, `save_app_settings` | `features/settings.py` |
| | `hydrate_env_from_supabase` | deleted (dead) |
| `supabase_store/transcripts/migrate.py` | `migrate_local_data` | `scripts/migrate_to_supabase.py` |

`set_status`, `append_transcript`, and `append_call_log` each exist twice (local records vs Supabase changes/transcript mixin). The Supabase copies differ only in `_all` / `_write` / `_touch` versus `self.leads` / `self.save`. The merged rule calls the backend for load and save. Do not "fix" the Supabase `add_csv` total (see "Noticed, not fixed"); keep each backend's `add_csv` accounting as it is, with the shared validation only.

### Dialer

`TwilioDialer` public and private methods, and where they go. Phase 5 dumps this list again before editing and shows the after locations.

| Method | Target |
| --- | --- |
| `__init__` | `DialerState` in `_dialer/state.py` |
| `public_state` | `_dialer/projection.py` |
| `live_state` | `_dialer/projection.py` |
| `_save_session`, `_bump`, `record_activity` | `features/dialer.py` (thin) or `projection.py` if they only serve projection. `_bump` and `_save_session` are used by queue and events; they live in `features/dialer.py` as functions the parts call, and parts do not import `dialer.py`. So they live in `_dialer/session_stats.py` (`_save_session`) and `features/metrics.py` is called directly for `_bump`. `record_activity` writes `state.activity_log` and lives in `_dialer/state.py` next to the log. |
| `_pool_leads`, `set_timezone_filter` | `_dialer/queue.py` |
| `_values`, `settings_state`, `save_settings` | `features/settings.py` (dialer holds the values dict and calls settings) |
| `validate_webhook`, `_url`, `_next_caller`, `_launch_call`, `_create_call`, `_cancel_call`, `_hangup_call` | `_dialer/twilio_api.py` for the HTTP/TwiML/signature pieces that do not touch dialer state. `_next_caller`, `_launch_call`, `_create_call`, `_cancel_call` touch `state` (`caller_index`, `in_flight`, `paused`, `running`). Those four stay in `_dialer/queue.py` and call `twilio_request` from `twilio_api.py`. `validate_webhook`, `_url`, `_hangup_call` are pure helpers in `twilio_api.py` and receive credentials and the URL as arguments. |
| `_transfer` | deleted (dead) |
| `start`, `_new_call` | `_dialer/queue.py`. `_new_call` builds the Call dict. |
| `_watch_token`, `_release_tokens`, `voice_access_token`, `handle_client_voice` | token math and AccessToken request → `twilio_api.py`. `handle_client_voice` mutates state → `call_events.py`. `_watch_token` / `_release_tokens` use `state.token_index` → `queue.py` beside `_new_call`. |
| `handle_webhook`, `_uuid` | `call_events.py` |
| `_pickup`, `_machine_result` | `_call_events/pickup.py` |
| `_answer_detection_timeout` | deleted (dead) |
| `enter_live_line`, `_select_human` | deleted (dead). `webhooks/live.py` `LiveMixin` goes away. |
| `_live_twiml`, `_start_transcription`, `_transcription_event` | `_call_events/transcript.py` |
| `_call_ended`, `_agent_call_ended` | `_call_events/ended.py` |
| `pause`, `hangup_active`, `skip_active`, `stop` | `features/dialer.py` if they stay the public route API under ~60 lines each; otherwise `_dialer/queue.py` for pause/stop timers and the entry only delegates. They are the public methods routes call, so the entry functions delegate and the bodies live in `_dialer/queue.py` (pause/stop/advance) and `_call_events/ended.py` is not their home. `hangup_active` and `skip_active` live in `call_events.py` because they hang up the active call. |
| `live_outcome_lead_id`, `choose_outcome`, `update_status` | `_dialer/outcomes.py` |
| `dial_lead`, `_dialable_lead`, `_claim_manual_lead`, `_pin_manual_dial` | `_dialer/queue.py` |
| `fill_slots` | `_dialer/_queue/slots.py` |
| `_schedule_advance`, `_advance_queue`, `advance_now`, `_schedule_calling_window_check`, `_check_calling_window` | `_dialer/_queue/timing.py` |
| `TokenIndex.__init__`, `register`, `forget`, `lookup` | `_dialer/twilio_api.py`. Accounts owns the instance. |
| `TwilioError`, `twilio_request`, `normalize_phone`, `escape_xml` | `_dialer/twilio_api.py` |
| `DIALER_DEFAULTS`, `_preferences` | `features/settings.py` (keys from vocabulary) |
| `read_env`, `write_env` | `shared/config.py` |
| `TWILIO_API` | `_dialer/twilio_api.py` |

Mixin classes themselves (`CoreMixin`, `StateMixin`, `SettingsMixin`, `ClientMixin`, `TokenMixin`, `VoiceMixin`, `StartMixin`, `WebhookMixin`, `DispatchMixin`, `PickupMixin`, both `LiveMixin`s, `TranscriptMixin`, `EndedMixin`, `LifecycleMixin`, `ControlsMixin`, `QueueMixin`, `ManualDialMixin`, `SlotMixin`, `AdvanceTimingMixin`, `OutcomeMixin`, `TwilioDialer`) are deleted as the composition. `TokenIndex` and `TwilioError` remain real classes.

There are two classes named `LiveMixin`: `twilio_calls/webhooks/live.py` (dead enter-live path) and `twilio_calls/transcript/live.py` (live TwiML and transcription, which stays).

### Tests today

| Current | Target |
| --- | --- |
| `tests/__init__.py` | stays |
| `tests/test_dialer_session/__init__.py` `DialerSessionTests` | deleted after merge |
| `part_1.test_call_tokens_route_to_the_dialer_that_created_them` | `tests/test_dialer.py` |
| `part_1.test_blank_preference_values_keep_defaults` | `tests/test_settings.py` |
| `part_1.test_stage_transitions_use_explicit_state_priority` | `tests/test_dialer.py` |
| `part_1.test_disposition_mapping` | `tests/test_dialer.py` |
| `part_1.test_local_time_and_calling_window_respect_prospect_timezone` | `tests/test_dialer.py` |
| `part_1.test_session_statistics_and_conversation_threshold` | `tests/test_dialer.py` |
| `part_1.test_session_history_persists_in_local_metrics_store` | `tests/test_metrics.py` |
| `part_1.test_call_flow_settings_persist_and_validate` | `tests/test_settings.py` |
| `part_2.test_signed_in_settings_are_saved_to_the_account` | `tests/test_settings.py` |
| `part_2.test_callback_is_persisted_and_do_not_call_leaves_the_auto_dial_pool` | `tests/test_dialer.py` (asserts both store and pool; do not split the assertion) |
| `part_2.test_any_pickup_connects_and_a_long_live_call_counts_as_a_conversation` | `tests/test_dialer.py` |
| `part_3.test_answer_bridges_any_pickup_and_keeps_voicemail_on_the_line` | `tests/test_dialer.py` |
| `part_3.test_rep_can_manually_enter_listening_line` | deleted (dead-code test) |
| `part_3.test_slow_answer_detection_does_not_drop_the_line` | deleted (dead-code test) |
| `part_4` all three manual-dial / caller-id tests | `tests/test_dialer.py` |
| `tests/test_supabase_store.py` `jwt_with_role` and the seven client tests | `tests/test_accounts.py` |
| `test_settings_round_trip_uses_dialer_settings_table` | `tests/test_settings.py` |
| `tests/test_transcript_storage/` `Part1`, `Part2`, `fixtures.FakeSupabaseClient`, `prospect` | `tests/test_prospects.py` (fixtures included). Package deleted. |

Patch targets change to the new modules. Assertions do not.

### Frontend

JS re-export files (`controllers/dialer/index.js`, `features/voice/device/index.js`, `views/dialer/call-stage/index.js`, `views/prospects-table/index.js`) are deleted with `static/js/`.

| Current | Symbols | Target |
| --- | --- | --- |
| `static/js/main.js` | boot sequence, no defs | `static/main.js` |
| `static/js/api/client.js` | `onUnauthorized`, `setUnauthorizedHandler`, `debugEvent`, `request`, `postJson`, `bindDebugListeners` | `static/_core/api.js` |
| `static/js/store/state.js` | `state` | `static/_core/store.js` (shared server snapshot) |
| | `S` keys used by one feature | that feature's module. Keys used by 2+ features stay in the core store. Phase 6 lists the split in the commit message after a reader scan; do not guess a key into core if only one feature reads it. |
| | `selectedLeadIds` | prospects |
| | `statMemory` | performance |
| | `seenSensoryActivity` | arcade |
| | `audioInputStorageKey`, `audioOutputStorageKey` | dialer voice |
| `static/js/utils/format.js` | `STATUS_*` | vocabulary JSON via core |
| | `byId`, `setText`, `initials`, `statusDate`, `formatMinutes`, `dayLabel` | `static/_core/dom.js` |
| `static/js/utils/notify.js` | `showToast` | `static/_core/dom.js` |
| `static/js/utils/phone.js` | `formatPhoneNumber` | `static/_core/dom.js` |
| `static/js/utils/time.js` | `localDateTimeParts`, `nextBusinessCallback`, `timezoneFor`, `localDateTimeToUtc` | `static/_core/time.js`. `timezoneFor` reads vocabulary. |
| `static/js/controllers/navigation.js` | `setDashboardTab`, `setPerformanceMode`, `bindNavigation` | `static/core.js` registry. Performance mode is registered by `performance.js`; the tab list is data, not a feature import. |
| `static/js/views/render.js` | `render` | `static/core.js` calls registered renderers. The signature check around `crmTableSignature` stays with the prospects renderer. |
| `static/js/controllers/poller.js` | `refreshState`, `startPolling` | `static/core.js` (it updates the shared snapshot and then renders). `processSensoryActivity` → `arcade.js`, invoked through the registry from the poller. |
| `static/js/controllers/keyboard.js` | `bindKeyboard` | `static/features/dialer.js` |
| `static/js/controllers/outcomes.js` | `submitOutcome`, `bindOutcomes` | `static/features/dialer.js` |
| `static/js/controllers/dialer/bindings.js` | `bindDialer` | `static/features/dialer.js`. Delete the `enterLiveButton` listener in phase 3. |
| `static/js/controllers/dialer/connect.js` | `prospectLabel`, `connectBrowserCall` | `static/features/_dialer/voice.js` |
| `static/js/controllers/dialer/lead.js` | `dialLead` | `static/features/dialer.js` |
| `static/js/controllers/dialer/session.js` | `startDialing` | `static/features/dialer.js` |
| `static/js/features/voice/device/connect.js` | `createVoiceDevice`, `bindVoice` | `_dialer/voice.js` |
| `static/js/features/voice/device/devices.js` | `setMicLevel`, `populateAudioSelect`, `refreshAudioDevices`, `routeTestAudio`, `twilioHasDevice`, `twilioDeviceEntries`, `resolveTwilioDeviceId`, `waitForTwilioAudioDevices`, `applyVoiceAudioDevices` | `_dialer/_voice/devices.js` |
| `static/js/features/voice/testing/index.js` | `startMicrophoneTest`, `stopMicrophoneTest`, `testAudioOutput` | `_dialer/_voice/testing.js` |
| `static/js/views/dialer/index.js` | `renderDialer` | `dialer.js` registers it. Drop the `"connecting"` alternative in phase 3; keep the rest of the expression. |
| `static/js/views/dialer/card.js` | `drawProspectWaveform`, `stopProspectWaveform`, `startProspectWaveform`, `renderDialedProspect` | `_dialer/stage.js`. Remove `"listening"` from the state list in phase 3. |
| `static/js/views/dialer/controls.js` | `renderDialerControls` | `_dialer/session_ui.js` |
| `static/js/views/dialer/outcome.js` | `renderOutcomeRow` | `_dialer/session_ui.js` |
| `static/js/views/dialer/queue.js` | `renderQueueStrip` | `_dialer/session_ui.js`. Drop `"connecting"` in phase 3. |
| `static/js/views/dialer/session-goal.js` | `renderSessionMomentum`, `bindSessionGoal` | `_dialer/session_ui.js` |
| `static/js/views/dialer/call-stage/stage.js` | `renderCallStage` | `_dialer/stage.js` |
| `static/js/views/dialer/call-stage/timer.js` | `stopCallTimer`, `startCallTimer` | `_dialer/stage.js` (22 lines, same UI as the stage; do not make a file for it) |
| `static/js/views/monitor/index.js` | `renderCallMonitor`, `bindCallMonitor` | `_dialer/session_ui.js`. Delete `waitingCall` / `enterLiveButton` / `"listening"` in phase 3. |
| `static/js/views/pool/index.js` | `renderTimezoneFilters`, `renderCallerPool` | `dialer.js` (pool is the dialer surface) |
| `static/js/controllers/pool.js` | `selectTimezone` | `dialer.js` |
| `static/js/views/dialogs/index.js` | `startNewSession`, `setStartNewSession`, `showSessionSummary`, `bindDialogs` | session summary → `dialer.js`. `setStartNewSession` is the registry pattern already; keep that shape in core. |
| `static/js/controllers/prospects.js` | `bindProspects`, `changeLeadStatus`, `deleteSelectedProspects` | `prospects.js` |
| `static/js/controllers/add-prospect.js` | `STANDARD_FIELDS`, `bindAddProspect`, `openAddProspectDialog`, `closeAddProspectDialog`, `textField`, `statusField`, `fieldValue`, `saveProspect` | `_prospects/csv.js` |
| `static/js/controllers/csv.js` | `importCsv`, `bindCsv` | `_prospects/csv.js` |
| `static/js/controllers/prospect-menu.js` | `bindProspectMenu` | `prospects.js` |
| `static/js/views/prospects-table/query.js` | `importedColumns`, `filteredLeads`, `crmTableSignature` | `_prospects/table.js` |
| `static/js/views/prospects-table/render.js` | `renderTable` | `_prospects/table.js` |
| `static/js/views/prospects-table/rows.js` | `appendLeadRows` | `_prospects/table.js` |
| `static/js/utils/transcript.js` | `transcriptTimestamp`, `renderTranscriptEntries`, `openTranscript`, `downloadTranscript` | `_prospects/transcript.js` |
| `static/js/views/metrics/index.js` | `rememberStat`, `renderMetrics` | `performance.js` |
| `static/js/views/metrics/charts.js` | `buildMetricsLineChart`, `pieSlicePath`, `buildStatusPieChart`, `buildConnectionPieChart` | `performance.js` if the sum stays under ~250, else `static/features/_performance/charts.js` |
| `static/js/controllers/settings.js` | `SECRET_FIELDS`, `applySavedSettings`, `maskSecrets`, `openSettings`, `bindSettings` | `settings.js`. Secret key list comes from vocabulary. |
| `static/js/controllers/auth.js` | `showLoginGate`, `hideLoginGate`, `syncAccountChrome`, `bootApp`, `initAuth`, `bindAuth` | `auth.js` |
| `static/js/features/arcade/controller/index.js` | `ArcadeSensoryController`, `arcadeSensory`, `startArcade` | `arcade.js`. The mixin expression is the composition rewrite. |
| `static/js/features/arcade/controller/shell.js` | `ArcadeCore.constructor`, `loadPreferences`, `syncControls`, `updatePreferences`, `schedule`, `clearTimers`, `stop` | `_arcade/shell.js` as functions on one state object |
| `static/js/features/arcade/controller/playback.js` | `PlaybackMixin`, `animateValue`, `reset`, `flashFailure` | `_arcade/playback.js` |
| `static/js/features/arcade/fx/audio.js` | `celebrateBooked`, `playCue`, `AudioMixin.canPlaySound`, `playTick`, `playRewardChime`, `playResetTone`, `vibrate` | `_arcade/audio.js`. `celebrateBooked` is called from dialer views today; dialer fires a core event, arcade subscribes. Dialer does not import arcade. |
| `static/js/features/arcade/fx/reels.js` | `ReelsMixin.stopTicking`, `startSpin`, `startTicking`, `match` | `_arcade/reels.js` |
| `static/js/features/arcade/fx/particles.js` | `ParticlesMixin.resizeCanvas`, `burstParticles`, `drawParticles`, `stopParticles` | `_arcade/particles.js` |

HTML:

| Current | Target |
| --- | --- |
| `static/app-shell/chrome.html` | `static/shell.html` |
| `static/app-shell/dialer.html` | `static/features/dialer.html` |
| `static/app-shell/metrics.html` performance panel | `static/features/performance.html` |
| `static/app-shell/metrics.html` prospects panel | `static/features/prospects.html` |
| `static/app-shell/metrics.html` pool panel | `static/features/_dialer/pool.html` |
| `static/app-shell/dialogs.html` | split into the feature that owns each top-level dialog (settings, add-prospect, session summary). Reorder allowed. |

CSS, in today's link order. Phase 6 merges rules into the feature file only when the same selector and same media block are combined so later declarations still win. If Playwright cannot be installed, do not merge: rename and relocate each file, keep this order, and record consolidation as follow-up.

| Current | Target |
| --- | --- |
| `static/css/01-tokens.css` | `static/base.css` |
| `static/css/02-layout.css` | `static/base.css` |
| `static/css/03-controls.css` | `static/base.css` plus feature files where a selector is feature-owned |
| `static/css/04-call-monitor.css` | `static/features/dialer.css`. Delete `.monitor-enter-live` and `[data-state="listening"]` in phase 3. |
| `static/css/05-charts.css` | `static/features/performance.css` |
| `static/css/06-dialogs.css` | split across settings, prospects, dialer dialog rules |
| `static/css/07-responsive.css` | stays last among shared rules inside `base.css`, after feature sheets if a query must still win. Order is verified by the pixel check. |
| `static/css/08-arcade.css` | `static/features/arcade.css` |
| `static/css/09-shell.css` | `static/base.css` |
| `static/css/linear/shell.css` | `static/base.css` (later than `09-shell.css`) |
| `static/css/linear/document.css` | `static/base.css` |
| `static/css/linear/controls.css` | `static/base.css` / feature css, preserving source order |
| `static/css/linear/monitor.css` | `static/features/dialer.css` after `04-call-monitor.css` rules |
| `static/css/linear/metrics.css` | `static/features/performance.css` and prospects table rules in `prospects.css`, source order preserved |

### Scripts and docs

| Current | Target |
| --- | --- |
| `scripts/migrate_to_supabase.py` `main` | stays; calls the moved `migrate_local_data` in the same file |
| `scripts/check_js_urls.py` `visit` | deleted in phase 7 after `scripts/check_static.py` covers it |
| `docs/supabase/schema.sql` | stays |
| `docs/supabase/setup.md` | stays |
| `docs/linear-design-system/**` | stays |

## (f) Risks and how each phase checks them

| Phase | Risk | Check |
| --- | --- | --- |
| 0 | done | branch `refactor/feature-slices`, clean diff, 37 tests OK, commit `refactor(phase 0): test discovery` |
| 2 | Frozen JSON keys or hook flow drift from production | `tests/test_http.py` and `tests/test_call_flow.py` pass on unmodified code. `docs/page-before.html` saved from `GET /`. `python scripts/check_static.py` passes. |
| 3 | Deleting a live branch | Re-run the searches below and require no remaining callers outside the definition. Suite stays green after removing only the two named tests. |
| 4 | Vocabulary JSON changes the page; schema drift | New test: metric-key lists in `schema.sql` equal `METRIC_KEYS`. `import server` works. Suite green. Page diff is only the allowlisted script. |
| 5 | Mixin rewrite changes a branch; cycle via settings keys | Before dialer edit, print sorted public and private method names of `TwilioDialer`. After, map each to the table in section (a). One commit per feature, suite green, old package deleted in that same commit. `python -c "import server"` must not import a deleted package. |
| 6 | CSS cascade or HTML move changes pixels; dialog reorder | Normalized `GET /` matches `page-before.html` under the allowlist. Playwright at 1440×900 and 390×844, every tab and every dialog, 0 differing pixels against screenshots taken at the start of phase 6 (after phase 5, so dead-code removal is already in both). If Playwright cannot be installed, skip the merge and log follow-up. |
| 7 | A new import cycle | `tests/test_architecture.py` runs `scripts/check_architecture.py`. |

Dead-code searches phase 3 re-runs (py, js, html, css, tests, scripts, docs; skip `Claude outputs/`):

- `listening` — assignments of `call["state"]` are only `creating` (in the `_new_call` literal), `ringing`, `live`, `cancelled`, `ended`, `skipped`. Nothing assigns `listening`. Readers to delete: `twilio_calls/webhooks/live.py`, `dialer/state.py` tuple, `lifecycle/controls.py` tuple, `static/js/views/monitor/index.js`, `static/js/views/dialer/card.js`, `static/css/04-call-monitor.css`, test `test_rep_can_manually_enter_listening_line`.
- `enter-live` / `enter_live_line` / `enterLive` — only `routes/ui/write.py`, `webhooks/live.py`, `static/js/controllers/dialer/bindings.js`, `static/app-shell/dialer.html`, the monitor view, `S.enteringLiveLine` in `store/state.js`.
- `winner` — only `webhooks/dispatch.py` and `_select_human`'s `_url(call, "winner")`.
- `_transfer` — defined as `@staticmethod` with a `self` parameter in `client/calls.py`, called only from `_select_human`.
- `answer_detection` — key set to `None` in `_new_call`; cancelled in `pickup.py`, `transcript/ended.py`, `webhooks/live.py`; `_answer_detection_timeout` called only from `test_slow_answer_detection_does_not_drop_the_line`.
- `CallStatus == "answered"` — the branch in `webhooks/dispatch.py` only. Do not remove `StatusCallbackEvent`'s `"answered"`.
- `hydrate_env_from_supabase` — definition plus exports in `supabase_store/__init__.py` and `transcripts/__init__.py`. No caller.
- `migrate` — parameter of `AppRuntime.configure` and the `migrate=True` argument in `server.py`. `migrate_local_data` stays.
- `"connecting"` — `static/js/views/dialer/index.js` and `static/js/views/dialer/queue.js` only. Server never sets that state.

Tests deleted by name:

- `tests.test_dialer_session.DialerSessionTests.test_rep_can_manually_enter_listening_line`
- `tests.test_dialer_session.DialerSessionTests.test_slow_answer_detection_does_not_drop_the_line`

After every phase: full suite, `python scripts/check_static.py` (exists from phase 2 on), `python -c "import server"`, commit `refactor(phase N): <summary>`.

## Noticed, not fixed

1. `supabase_store/leads/changes.py` `add_csv` sets `info["total"] = len(leads) + len(additions)` after `leads.extend(additions)`, so the reported total counts new rows twice. Local `RecordMixin.add_csv` sets `info["total"] = len(self.leads)` after extend and does not double-count. Keep both behaviors.
2. `core/dialer_session.py` `session_summary` assigns `result["current_streak"] = result.get("best_streak", 0)` and then `result.pop("current_streak", None)`. The assignment has no effect. Leave it.
3. `_transfer` is a `@staticmethod` that takes `self`. Calling it as `self._transfer(uuid, url)` raises `TypeError`. Phase 3 deletes it as dead; that is not a fix of the staticmethod.
4. `AppRuntime.configure(migrate=False)` ignores `migrate`. `server.py` passes `migrate=True` and no migration runs. Phase 3 removes the unused parameter. `migrate_local_data` remains the script's job.
5. `StatusCallbackEvent` asks Twilio for `answered`, while `handle_webhook` treats `CallStatus == "answered"` as pickup and otherwise waits for `in-progress` (`action == "answer"`). Phase 3 deletes only the `CallStatus` branch, as specified. The subscription list stays.
6. Two different classes are named `LiveMixin`. The webhook one is dead. The transcript one is live. Renaming is not required once they live in different functions; do not rename for style.
7. Supabase `add_csv` total bug aside, `set_status` / `append_transcript` / `append_call_log` match between local and Supabase except for how they load and save. Merge the rules; do not unify the `add_csv` total.
