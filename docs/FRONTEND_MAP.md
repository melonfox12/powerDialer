# Frontend map

Phase 6 plan for the browser. Behavior stays the same. Moves change imports and how a part reaches shared state. CSS files and `<link>` tags stay put in this chat.

Startup order in `static/js/main.js` today, and the order `static/main.js` must keep:

1. `bindDebugListeners`
2. `startArcade`
3. `bindNavigation`
4. `bindDialogs`
5. `bindProspects`
6. `bindAddProspect`
7. `bindProspectMenu`
8. `bindSettings`
9. `bindCsv`
10. search input and status filter → `renderTable`
11. `bindCallMonitor`
12. `bindSessionGoal`
13. `bindDialer`
14. `bindKeyboard`
15. `bindOutcomes`
16. arcade preference inputs → `arcadeSensory.updatePreferences`
17. `bindVoice`
18. `bindAuth`
19. `initAuth` (failure calls `showLoginGate`)
20. `startPolling`

Feature order: `arcade → settings → performance → dialer → prospects → auth`. A feature imports only entries to its left, or `static/core.js`. Core imports no feature. Cross-feature effects go through core registries (`registerRenderer`, `registerTab`, `onUnauthorized`, `onSensoryActivity`).

The poller is a dialer file in this chat (`static/features/_dialer/poller.js`), not core. It imports `arcade.js` for `reset()` on a failed call. Dialer is to the right of arcade, so that import is legal. `processSensoryActivity` stays next to the poller.

## Shared `state` and `S`

The server snapshot object `state` stays in core. The poller replaces its fields in one `Object.assign`. Splitting the object would change that update. Fields read by only one feature still live on that object.

`S` fields used by two or more features stay in core. The rest move beside the feature that reads them.

| Field | Readers | Home |
| --- | --- | --- |
| `S.accessToken`, `S.googleAuthEnabled` | `api/client.js` (core) and `controllers/auth.js` | core. The client sends the token on every request. |
| `S.audioContext` | arcade `fx/audio.js`, dialer voice `connect.js`, dialer `card.js` | core |
| `S.userInteracted` | arcade `fx/audio.js`, dialer voice `connect.js` | core |
| `S.micTestRecorder` | `controllers/settings.js`, dialer voice `connect.js` and `testing/index.js` | core |
| `S.lastCrmTableSignature` | `views/render.js`, prospects table `render.js` | prospects. The signature check stays with the prospects renderer, as in the architecture map. Core's `render` calls the registered prospects renderer, which owns the comparison. |
| `S.voiceDevice`, `S.voiceCall`, `S.waveformAnalyser` | dialer controllers, voice, `card.js` only | dialer |
| `S.outcomeSubmitting` | keyboard, outcomes, outcome row | dialer |
| `S.keptLineId` | bindings, controls, monitor | dialer |
| `S.selectionAnchorId` | prospects controller, table render, rows | prospects |
| `S.micTestStream`, `S.micTestContext`, `S.micTestFrame`, `S.micTestChunks`, `S.micPeakLevel`, `S.micClippingFrames`, `S.micPlaybackUrl` | voice testing only | dialer |
| `S.callTimerId`, `S.connectedAt`, `S.previousStage`, `S.waveformFrame`, `S.waveformSource` | call stage / timer / card | dialer |
| `S.celebratedSessionId`, `S.dismissedBreakForSession`, `S.goalCelebrated`, `S.halfwaySessionId`, `S.halfwayTimer`, `S.previousMeetings`, `S.previousSessionConversations` | session goal only | dialer |
| `S.observedActiveLeadId` | dialer `index.js` only | dialer |
| `S.lastLiveTranscriptKey` | monitor only | dialer |
| `S.dashboardTab`, `S.performanceMode` | navigation only | core. The tab registry lives in core and these are its current tab. |
| `S.pollBusy`, `S.metricsFetchedAt`, `S.sensoryActivityPrimed` | poller only | dialer, beside the poller |
| `S.supabaseClient` | auth only | auth |
| `selectedLeadIds` | prospects | prospects |
| `statMemory` | performance `rememberStat` | performance |
| `seenSensoryActivity` | poller | dialer |
| `audioInputStorageKey`, `audioOutputStorageKey` | voice devices | dialer |

## Function homes

Core (`static/core.js` and `static/_core/`):

| Current | Target |
| --- | --- |
| `api/client.js` `setUnauthorizedHandler`, `debugEvent`, `request`, `postJson`, `bindDebugListeners` | `static/_core/api.js` |
| `utils/format.js` exports | `static/_core/format.js` |
| `utils/notify.js` `showToast` | `static/_core/notify.js` |
| `utils/phone.js` `formatPhoneNumber` | `static/_core/phone.js` |
| `utils/time.js` exports | `static/_core/time.js` |
| `utils/transcript.js` `transcriptTimestamp`, `renderTranscriptEntries` | `static/_core/transcript.js` |
| `store/state.js` shared `state` and the core `S` fields | `static/_core/state.js` |
| `views/render.js` `render` | `static/core.js` registry. It calls registered renderers and does not import features. |
| `controllers/navigation.js` `setDashboardTab`, `setPerformanceMode`, `bindNavigation` | `static/core.js` tab registry |

Arcade (`static/features/arcade.js`, parts in `static/features/_arcade/`):

| Current | Target |
| --- | --- |
| `features/arcade/controller/shell.js` `ArcadeCore` | `_arcade/shell.js` functions `(arcade)` |
| `features/arcade/controller/playback.js` `PlaybackMixin` | `_arcade/playback.js` |
| `features/arcade/fx/audio.js` `AudioMixin`, `celebrateBooked`, `playCue` | `_arcade/audio.js`. `celebrateBooked` and `playCue` stay exported from `arcade.js` |
| `features/arcade/fx/reels.js` `ReelsMixin` | `_arcade/reels.js` |
| `features/arcade/fx/particles.js` `ParticlesMixin` | `_arcade/particles.js` |
| `features/arcade/controller/index.js` `ArcadeSensoryController`, `arcadeSensory`, `startArcade` | `arcade.js` |

No two arcade mixins define the same method name. `stop` exists only on `ArcadeCore`. `reset` exists only on `PlaybackMixin`. `stopTicking` and `stopParticles` are different names. Nothing is dropped as an override.

Settings: `controllers/settings.js` `applySavedSettings`, `openSettings`, `bindSettings` → `static/features/settings.js`. `bindSettings` calls `arcadeSensory.syncControls()`. Settings is to the right of arcade, so it imports `arcade.js`.

Performance: `views/metrics/index.js` `rememberStat`, `renderMetrics` and `views/metrics/charts.js` `buildMetricsLineChart`, `pieSlicePath`, `buildStatusPieChart`, `buildConnectionPieChart` → `static/features/performance.js` if the sum stays under about 250 lines, otherwise charts stay in `static/features/_performance/charts.js`. Registers itself with core's renderer and tab registry. Imports no feature.

Dialer (`static/features/dialer.js` and `static/features/_dialer/`):

| Current | Target |
| --- | --- |
| `controllers/dialer/index.js` | entry re-exports `bindDialer` wiring |
| `controllers/dialer/bindings.js` `bindDialer` | `_dialer/bindings.js` |
| `controllers/dialer/session.js` `startDialing` | `dialer.js` |
| `controllers/dialer/lead.js` `dialLead` | `dialer.js` |
| `controllers/dialer/connect.js` `prospectLabel`, `connectBrowserCall` | `_dialer/voice.js` |
| `controllers/outcomes.js` `submitOutcome`, `bindOutcomes` | `_dialer/outcomes.js` |
| `controllers/keyboard.js` `bindKeyboard` | `_dialer/keyboard.js` |
| `controllers/poller.js` `processSensoryActivity`, `refreshState`, `startPolling` | `_dialer/poller.js` |
| `controllers/pool.js` `selectTimezone` | `_dialer/pool.js` |
| `views/dialer/**` | `_dialer/stage.js` and `_dialer/session_ui.js` |
| `views/monitor/index.js` | `_dialer/session_ui.js` |
| `views/pool/index.js` | `_dialer/pool.js` |
| `views/dialogs/index.js` `showSessionSummary`, `setStartNewSession` | `_dialer/summary.js` |
| `features/voice/**` | `_dialer/voice.js`, `_dialer/_voice/devices.js`, `_dialer/_voice/testing.js` |

`startDialing` and `dialLead` share `connectAndCleanup` in `_dialer/connect.js`. Both public behaviors stay the same. The two functions stay in `_dialer/session.js` and `_dialer/lead.js`, and `dialer.js` re-exports them. `bindings.js` calls `startDialing`, and a part cannot import the entry.

Views stay as separate files under `_dialer/` (`stage.js`, `timer.js`, `card.js`, `controls.js`, `queue.js`, `outcome-row.js`, `render-dialer.js`, `session-goal.js`, `monitor.js`, `pool-view.js`). Folding them into the two files named above would pass 250 lines. `pool.js` is the timezone controller. Voice lives in `_dialer/_voice/`.

`call-stage` and `session-goal` call `playCue` and `arcadeSensory` today. Those calls move to `dialer.js`. The view functions return what happened, or accept a callback the entry passes in. They do not import arcade.

Prospects:

| Current | Target |
| --- | --- |
| `controllers/prospects.js` | `prospects.js` |
| `controllers/add-prospect.js`, `controllers/csv.js` | `_prospects/csv.js` |
| `controllers/prospect-menu.js` | `_prospects/table.js` |
| `views/prospects-table/**` | `_prospects/table.js` |
| `utils/transcript.js` `openTranscript`, `downloadTranscript` | `_prospects/transcript.js` |
| `views/dialogs/index.js` transcript dialog | `_prospects/transcript.js` |

Auth: `controllers/auth.js` → `static/features/auth.js`. It calls `setUnauthorizedHandler` on core. Core does not import auth. `onUnauthorized` is the registry.

## Cross-feature calls after the move

| Call | Direction | How |
| --- | --- | --- |
| Settings `syncControls` | settings → arcade | direct import of `arcade.js` |
| Dialer stage sounds, outcome `celebrateBooked`, poller `reset` | dialer → arcade | `dialer.js` and `_dialer/poller.js` import `arcade.js`. View files do not. |
| Main arcade preference inputs | main → arcade | `static/main.js` calls `arcade.js` during boot, same as today |
| Poller `render` | dialer → core | core registry runs performance, dialer, and prospects renderers |
| Navigation tab change | core | `registerTab`. Performance registers its mode. Core does not import performance. |
| Unauthorized responses | auth → core | auth passes `showLoginGate` to `setUnauthorizedHandler` |
| Prospects table refresh | core render → prospects | prospects `registerRenderer` |

No edge points right-to-left.

## HTML

Partial order that `GET /` concatenates, matching today's body order:

1. `static/shell.html` from `app-shell/chrome.html`
2. `static/features/dialer.html` from `app-shell/dialer.html`, plus the session-summary `<dialog>`
3. `static/features/performance.html` the performance panel from `metrics.html`
4. `static/features/prospects.html` the prospects panel, the caller-pool panel, and the add-prospect and transcript dialogs
5. `static/features/settings.html` the settings `<dialog>`
6. `static/shell-end.html` the closing tags

The caller-pool panel stays inside `prospects.html`. Moving it to `dialer.html` would place it before the performance and prospects panels. The page-equality allowlist forbids that move. Top-level dialogs may be reordered. CSS `<link>` tags stay byte-identical. The module script `src` may change from `js/main.js` to `main.js`.

The partial list the server concatenates lives in `_web/respond.py` (`send_app_page`), not in `web.py`. This chat updates that list. `web.py` does not contain it.

## Noticed, not fixed

1. `render` in `views/render.js` hides `#headingImportButton` from `state.leads.length` on every poll, including when the table signature did not change.
2. `session-goal.js` calls `arcadeSensory.burstParticles()` only when arcade is enabled, from inside the view. The move keeps that condition and only changes which file performs the call.
