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

const renderers = [];
let callerPoolRenderer = () => {};

export function registerRenderer(fn, position = "end") {
  if (position === "start") renderers.unshift(fn);
  else renderers.push(fn);
}

let tableRenderer = () => {};

export function registerTable(fn) {
  tableRenderer = fn;
}

export function renderTable() {
  tableRenderer();
}

export function runRenderers() {
  for (const fn of renderers) fn();
}

export function registerCallerPool(fn) {
  callerPoolRenderer = fn;
}

export function renderCallerPool() {
  callerPoolRenderer();
}

export {
  state,
  S,
  statMemory,
  seenSensoryActivity,
  audioInputStorageKey,
  audioOutputStorageKey,
} from "./_core/state.js";
