export {
  setUnauthorizedHandler,
  debugEvent,
  request,
  postJson,
  bindDebugListeners,
} from "./_core/api.js";
export {
  STATUS_STYLES,
  STATUS_LABELS,
  STATUS_COLOR_VARS,
  STATUS_KEYS,
  TIMEZONE_NAMES,
  SECRET_INPUTS,
  byId,
  setText,
  initials,
  statusDate,
  formatMinutes,
  dayLabel,
} from "./_core/format.js";
export { showToast } from "./_core/notify.js";
export { formatPhoneNumber } from "./_core/phone.js";
export {
  localDateTimeParts,
  nextBusinessCallback,
  timezoneFor,
  localDateTimeToUtc,
} from "./_core/time.js";
export {
  transcriptTimestamp,
  renderTranscriptEntries,
  openTranscript,
  downloadTranscript,
  registerTranscriptActions,
} from "./_core/transcript.js";
let refreshAudioDevicesImpl = async () => {};
let stopMicrophoneTestImpl = async () => {};

export function registerAudioDevices(refresh, stop) {
  refreshAudioDevicesImpl = refresh;
  stopMicrophoneTestImpl = stop;
}

export function refreshAudioDevices() {
  return refreshAudioDevicesImpl();
}

export function stopMicrophoneTest() {
  return stopMicrophoneTestImpl();
}

export {
  registerRenderer,
  runRenderers,
  registerTable,
  renderTable,
  registerCallerPool,
  renderCallerPool,
} from "./_core/registry.js";
export { render } from "./_core/render.js";
export { bindNavigation, setDashboardTab, setPerformanceMode } from "./_core/navigation.js";

export {
  state,
  S,
  statMemory,
  seenSensoryActivity,
  audioInputStorageKey,
  audioOutputStorageKey,
} from "./_core/state.js";
