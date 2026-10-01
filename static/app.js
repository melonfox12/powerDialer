const STATUS_LABELS = {
  new: "New",
  call: "Call later",
  disqualified: "Disqualified",
  booked: "Booked",
};
const STATUS_COLOR_VARS = {
  new: "--success",
  call: "--amber",
  disqualified: "--red",
  booked: "--blue",
};

const state = {
  leads: [],
  pool: [],
  timezone_groups: [],
  selected_timezone: null,
  metrics: { today: {}, all_time: {}, daily: [] },
  counts: { total: 0, new: 0, calling: 0, booked: 0 },
  in_flight: [],
  pending_outcome: null,
  active_lead: null,
  running: false,
  paused: false,
  agent_ready: false,
  caller_ids: [],
  last_error: "",
  last_event: "Ready",
};

let toastTimer;
let pollBusy = false;
let outcomeSubmitting = false;
let dashboardTab = "performance";
let performanceMode = "summary";
let observedActiveLeadId = null;
let voiceDevice = null;
let voiceCall = null;
let micTestStream = null;
let micTestRecorder = null;
let micTestContext = null;
let micTestFrame = 0;
let micTestChunks = [];
let micPeakLevel = 0;
let micClippingFrames = 0;
let micPlaybackUrl = null;
const selectedLeadIds = new Set();
let selectionAnchorId = null;
const audioInputStorageKey = "prospect-desk-audio-input";
const audioOutputStorageKey = "prospect-desk-audio-output";

const byId = (id) => document.getElementById(id);

window.addEventListener("error", (event) => {
  console.error("Unhandled error:", event.error || event.message);
  showToast(`Unexpected error: ${event.message}`, true);
});
window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled promise rejection:", event.reason);
  showToast(`Unexpected error: ${event.reason?.message || event.reason}`, true);
});

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const type = response.headers.get("content-type") || "";
  const result = type.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(result?.error || `Request failed (${response.status})`);
  return result;
}

function postJson(path, payload = {}) {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

function setText(id, value) {
  byId(id).textContent = value;
}

function initials(name) {
  const words = (name || "").trim().split(/\s+/).filter(Boolean);
  return words.length > 1 ? `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase() : (words[0] || "?").slice(0, 2).toUpperCase();
}

function statusDate(lead) {
  if (!lead.scheduled_until) return "";
  const due = new Date(lead.scheduled_until);
  if (Number.isNaN(due.getTime())) return "";
  return due.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function transcriptTimestamp(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Time unavailable" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderTranscriptEntries(container, entries, emptyMessage) {
  if (!entries.length) {
    const empty = document.createElement("p");
    empty.className = "transcript-empty";
    empty.textContent = emptyMessage;
    container.replaceChildren(empty);
    return;
  }
  const ordered = [...entries].sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp));
  container.replaceChildren(...ordered.map((entry) => {
    const row = document.createElement("article");
    row.className = `transcript-entry transcript-entry-${String(entry.speaker || "unknown").toLowerCase()}`;
    const meta = document.createElement("div");
    meta.className = "transcript-entry-meta";
    const speaker = document.createElement("strong");
    speaker.textContent = entry.speaker || "Speaker";
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp);
    const text = document.createElement("p");
    text.textContent = entry.text || "";
    meta.append(speaker, timestamp);
    row.append(meta, text);
    return row;
  }));
}

function openTranscript(lead) {
  const entries = lead.transcript || [];
  byId("transcriptDialogTitle").textContent = `${lead.name || lead.business || lead.phone} · Transcript`;
  byId("transcriptDialogMeta").textContent = `${lead.phone || ""} · ${entries.length} utterance${entries.length === 1 ? "" : "s"}`;
  renderTranscriptEntries(byId("transcriptDialogBody"), entries, "No transcript has been captured for this call.");
  byId("transcriptDialog").showModal();
}

function importedColumns() {
  const columns = [];
  const standard = /^(name|full name|contact|first name|last name|business|company|organization|organisation|phone|mobile|cell|telephone|time\s?zone|tz|call.?status|status)$/i;
  for (const lead of state.leads) {
    for (const key of Object.keys(lead.fields || {})) {
      if (!standard.test(key) && !columns.includes(key)) columns.push(key);
    }
  }
  return columns;
}

function filteredLeads() {
  const query = byId("searchInput").value.trim().toLocaleLowerCase();
  const filter = byId("statusFilter").value;
  return state.leads.filter((lead) => {
    if (filter !== "all" && lead.status !== filter) return false;
    if (!query) return true;
    const values = [lead.name, lead.business, lead.phone, lead.status, ...Object.values(lead.fields || {})];
    return values.some((value) => String(value || "").toLocaleLowerCase().includes(query));
  });
}

function renderTable() {
  const head = byId("tableHead");
  const body = byId("tableBody");
  const leads = filteredLeads();
  const extras = importedColumns();
  const currentLeadIds = new Set(state.leads.map((lead) => lead.id));
  for (const id of selectedLeadIds) {
    if (!currentLeadIds.has(id)) selectedLeadIds.delete(id);
  }
  if (!currentLeadIds.has(selectionAnchorId)) selectionAnchorId = null;
  head.replaceChildren();
  body.replaceChildren();

  const selectAllCell = document.createElement("th");
  selectAllCell.className = "selection-cell";
  selectAllCell.scope = "col";
  const selectAll = document.createElement("input");
  selectAll.type = "checkbox";
  selectAll.className = "prospect-checkbox";
  selectAll.setAttribute("aria-label", "Select all visible prospects");
  const selectedVisibleCount = leads.filter((lead) => selectedLeadIds.has(lead.id)).length;
  selectAll.checked = leads.length > 0 && selectedVisibleCount === leads.length;
  selectAll.indeterminate = selectedVisibleCount > 0 && selectedVisibleCount < leads.length;
  selectAll.addEventListener("change", () => {
    for (const lead of leads) {
      if (selectAll.checked) selectedLeadIds.add(lead.id);
      else selectedLeadIds.delete(lead.id);
    }
    renderTable();
  });
  selectAllCell.append(selectAll);
  head.append(selectAllCell);

  for (const label of ["Prospect", "Company", "Phone", "Timezone", ...extras, "Call status", "Call transcript"]) {
    const cell = document.createElement("th");
    cell.scope = "col";
    cell.textContent = label;
    head.append(cell);
  }

  for (const lead of leads) {
    const row = document.createElement("tr");
    row.classList.toggle("selected", selectedLeadIds.has(lead.id));
    const selectionCell = document.createElement("td");
    selectionCell.className = "selection-cell";
    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "prospect-checkbox";
    checkbox.checked = selectedLeadIds.has(lead.id);
    checkbox.setAttribute("aria-label", `Select ${lead.name || lead.phone || "prospect"}`);
    checkbox.addEventListener("click", (event) => {
      const targetIndex = leads.findIndex((item) => item.id === lead.id);
      const anchorIndex = leads.findIndex((item) => item.id === selectionAnchorId);
      if (event.shiftKey && anchorIndex >= 0 && targetIndex >= 0) {
        const start = Math.min(anchorIndex, targetIndex);
        const end = Math.max(anchorIndex, targetIndex);
        for (const item of leads.slice(start, end + 1)) {
          if (checkbox.checked) selectedLeadIds.add(item.id);
          else selectedLeadIds.delete(item.id);
        }
      } else if (checkbox.checked) {
        selectedLeadIds.add(lead.id);
      } else {
        selectedLeadIds.delete(lead.id);
      }
      selectionAnchorId = lead.id;
      renderTable();
    });
    selectionCell.append(checkbox);
    row.append(selectionCell);

    const contact = document.createElement("td");
    const contactWrap = document.createElement("div");
    contactWrap.className = "contact-cell";
    const avatar = document.createElement("span");
    avatar.className = "contact-avatar";
    avatar.textContent = initials(lead.name || lead.business);
    const copy = document.createElement("span");
    copy.className = "contact-copy";
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const subline = document.createElement("span");
    subline.textContent = lead.business || "Prospect";
    copy.append(name, subline);
    contactWrap.append(avatar, copy);
    contact.append(contactWrap);
    row.append(contact);

    for (const value of [lead.business, lead.phone, lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value || "—";
      if (value === lead.phone) cell.className = "phone-cell";
      row.append(cell);
    }

    for (const column of extras) {
      const cell = document.createElement("td");
      cell.title = lead.fields?.[column] || "";
      cell.textContent = lead.fields?.[column] || "—";
      row.append(cell);
    }

    const statusCell = document.createElement("td");
    const select = document.createElement("select");
    select.className = `status-select status-${lead.status}`;
    select.setAttribute("aria-label", `Call status for ${lead.name || lead.phone}`);
    for (const value of ["new", "call", "booked", "disqualified"]) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value === "call" && statusDate(lead) ? `Call (${statusDate(lead)})` : STATUS_LABELS[value];
      option.selected = lead.status === value;
      if (value === "new" && state.pending_outcome?.id === lead.id) option.disabled = true;
      select.append(option);
    }
    select.addEventListener("change", () => changeLeadStatus(lead, select.value, select));
    statusCell.append(select);
    row.append(statusCell);

    const transcriptCell = document.createElement("td");
    const transcriptButton = document.createElement("button");
    const transcriptCount = lead.transcript?.length || 0;
    transcriptButton.type = "button";
    transcriptButton.className = "transcript-view-button";
    transcriptButton.textContent = transcriptCount ? `View · ${transcriptCount}` : "No transcript";
    transcriptButton.disabled = transcriptCount === 0;
    transcriptButton.setAttribute("aria-label", transcriptCount ? `View ${transcriptCount} transcript utterances for ${lead.name || lead.phone}` : `No transcript for ${lead.name || lead.phone}`);
    transcriptButton.addEventListener("click", () => openTranscript(lead));
    transcriptCell.append(transcriptButton);
    row.append(transcriptCell);
    body.append(row);
  }

  const empty = byId("emptyState");
  empty.classList.toggle("visible", leads.length === 0);
  empty.querySelector("h2").textContent = state.leads.length === 0 ? "Your CRM starts here" : "No matching prospects";
  empty.querySelector("p").textContent = state.leads.length === 0
    ? "Import a CSV to add prospects to your workspace."
    : "Change the search or status filter to see more rows.";
  empty.querySelector("[data-import]").hidden = state.leads.length > 0;
  byId("crmTable").hidden = state.leads.length === 0;
  const summary = `${leads.length} of ${state.leads.length} prospect${state.leads.length === 1 ? "" : "s"}`;
  setText("tableSummary", selectedLeadIds.size ? `${selectedLeadIds.size} selected · ${summary}` : summary);
  const deleteButton = byId("deleteSelectedButton");
  deleteButton.hidden = selectedLeadIds.size === 0;
  deleteButton.textContent = `Delete ${selectedLeadIds.size} selected`;
}

async function selectTimezone(timezone) {
  try {
    Object.assign(state, await postJson("/api/timezone", { timezone: timezone || "" }));
    render();
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderTimezoneFilters() {
  const groups = state.timezone_groups || [];
  const totalNew = groups.reduce((sum, group) => sum + group.count, 0);
  const selected = state.selected_timezone || "";
  const knownZones = groups.map((group) => group.name);
  const options = [new Option(`All time zones (${totalNew})`, "")];
  if (selected && !knownZones.includes(selected)) options.push(new Option(selected, selected));
  options.push(...groups.map((group) => new Option(`${group.name} (${group.count})`, group.name)));
  for (const select of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")].filter(Boolean)) {
    select.replaceChildren(...options.map((option) => option.cloneNode(true)));
    select.value = selected;
  }
}

function renderCallerPool() {
  const pool = state.pool || [];
  renderTimezoneFilters();
  setText("poolTabCount", String(pool.length));
  setText("poolTableSummary", `${pool.length} new prospect${pool.length === 1 ? "" : "s"}${state.selected_timezone ? ` · ${state.selected_timezone}` : ""}`);
  const body = byId("poolTableBody");
  body.replaceChildren(...pool.map((lead) => {
    const row = document.createElement("tr");
    const prospect = document.createElement("td");
    const contact = document.createElement("div");
    contact.className = "contact-copy";
    const name = document.createElement("strong");
    name.textContent = lead.name || "Unnamed prospect";
    const detail = document.createElement("span");
    detail.textContent = lead.business || "Prospect";
    contact.append(name, detail);
    prospect.append(contact);
    row.append(prospect);
    for (const value of [lead.business || "—", lead.phone || "—", lead.timezone || "Unknown"]) {
      const cell = document.createElement("td");
      cell.textContent = value;
      if (value === lead.phone) cell.className = "phone-cell";
      row.append(cell);
    }
    const status = document.createElement("td");
    const statusLabel = document.createElement("span");
    statusLabel.className = "pool-new-status";
    statusLabel.textContent = "New";
    status.append(statusLabel);
    row.append(status);
    const transcript = document.createElement("td");
    const button = document.createElement("button");
    const count = lead.transcript?.length || 0;
    button.type = "button";
    button.className = "transcript-view-button";
    button.textContent = count ? `View · ${count}` : "No transcript";
    button.disabled = count === 0;
    button.addEventListener("click", () => openTranscript(lead));
    transcript.append(button);
    row.append(transcript);
    return row;
  }));
  byId("poolTable").hidden = pool.length === 0;
  byId("poolTableEmpty").classList.toggle("visible", pool.length === 0);
}

function renderTranscriptTab() {
  const current = state.active_lead || state.pending_outcome;
  const recent = [...state.leads].filter((lead) => lead.transcript?.length).sort((left, right) => {
    const leftTime = left.transcript[left.transcript.length - 1]?.timestamp || "";
    const rightTime = right.transcript[right.transcript.length - 1]?.timestamp || "";
    return rightTime.localeCompare(leftTime);
  })[0];
  const lead = current || recent;
  const live = state.live_transcript || {};
  const partials = lead && live.lead_id === lead.id ? live.partials || [] : [];
  const entries = [...(lead?.transcript || []), ...partials];
  setText("transcriptTabLead", lead ? lead.name || lead.business || lead.phone : "Waiting for a connected prospect");
  setText("transcriptTabPhone", lead?.phone || "");
  setText("transcriptTabStatus", live.lead_id === lead?.id && live.transcribing ? "Live · partials enabled" : lead?.transcript?.length ? "Saved transcript" : "No active transcript");
  renderTranscriptEntries(byId("transcriptTabBody"), entries, "Transcript lines appear here after a prospect answers.");
}

function drawProspectWaveform(level = 0) {
  const canvas = byId("prospectWaveform");
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(bounds.width * ratio);
  const height = Math.round(bounds.height * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const normalized = Math.max(0, Math.min(1, level));
  const count = 44;
  const gap = 3;
  const barWidth = Math.max(2, (bounds.width - gap * (count - 1)) / count);
  const center = bounds.height / 2;
  context.fillStyle = normalized > 0.82 ? "#e1b76d" : "#4cc38a";
  for (let index = 0; index < count; index += 1) {
    const envelope = 0.18 + 0.82 * Math.abs(Math.sin(index * 0.38 + performance.now() / 120));
    const variation = 0.35 + Math.random() * 0.65;
    const barHeight = Math.max(2, normalized * bounds.height * envelope * variation);
    const x = index * (barWidth + gap);
    context.fillRect(x, center - barHeight / 2, barWidth, barHeight);
  }
  setText("prospectAudioLevel", `${Math.round(normalized * 100)}%`);
}

function renderCallMonitor() {
  const activity = state.activity_log || [];
  const activityList = byId("activityLog");
  setText("activityCount", `${activity.length} event${activity.length === 1 ? "" : "s"}`);
  activityList.replaceChildren(...activity.slice(-16).map((entry) => {
    const row = document.createElement("li");
    const timestamp = document.createElement("time");
    timestamp.dateTime = entry.timestamp || "";
    timestamp.textContent = transcriptTimestamp(entry.timestamp).replace(/:\d{2}$/, "");
    const source = document.createElement("span");
    source.className = `activity-source activity-source-${entry.source || "dialer"}`;
    source.textContent = entry.source || "dialer";
    const message = document.createElement("span");
    message.className = "activity-message";
    message.textContent = entry.message || "";
    row.append(timestamp, source, message);
    return row;
  }));
  activityList.scrollTop = activityList.scrollHeight;

  const lead = state.active_lead || state.pending_outcome;
  const liveTranscript = state.live_transcript || {};
  const matchingPartials = lead && liveTranscript.lead_id === lead.id ? liveTranscript.partials || [] : [];
  const segments = [...(lead?.transcript || []), ...matchingPartials];
  const status = lead
    ? liveTranscript.transcribing ? "Transcribing" : state.active_lead ? "Call connected" : "Call ended"
    : state.agent_ready ? "Waiting for prospect" : state.running ? "Connecting" : "Idle";
  setText("monitorStatus", status);
  setText("transcriptLiveStatus", liveTranscript.transcribing ? "Live · partials enabled" : lead ? "Final utterances saved" : "Waiting for a human answer");
  renderTranscriptEntries(
    byId("liveTranscript"),
    segments.slice(-8),
    lead ? "Waiting for the first utterance…" : "Utterances appear here during a connected call.",
  );
}

function renderDialer() {
  const connected = state.running && state.agent_ready;
  const pending = state.pending_outcome;
  const active = state.active_lead;
  const busy = state.running || Boolean(pending);
  const connection = byId("connectionState");
  connection.classList.toggle("busy", busy && !state.last_error);
  connection.classList.toggle("error", Boolean(state.last_error));
  connection.querySelector("span:last-child").textContent = state.last_error
    ? "Needs attention"
    : pending ? "Outcome needed" : state.paused ? "Paused" : connected ? "Dialing" : state.running ? "Connecting" : "Ready";

  const indicator = document.querySelector(".live-indicator");
  indicator.classList.toggle("on", connected && !state.paused);
  setText("liveLabel", pending ? "OUTCOME REQUIRED" : active ? "LIVE CALL" : state.paused ? "DIALER PAUSED" : connected ? "DIALING" : state.running ? "CONNECTING" : "DIALER STANDBY");
  setText("lineCount", `${state.in_flight?.length || 0} / 1 prospect`);
  setText("dialerMessage", state.last_error || (pending
    ? "Choose an outcome to continue dialing."
    : state.paused ? "Paused. Existing calls stay connected."
      : connected ? "One new prospect is called at a time."
        : state.running ? "Waiting for computer audio to connect."
          : state.last_event || "Your call session is stopped."));
  byId("dialerMessage").classList.toggle("error", Boolean(state.last_error));

  const target = active || (state.in_flight?.find((call) => call.state === "connecting")?.lead);
  const activeCall = byId("activeCall");
  activeCall.replaceChildren();
  const avatar = document.createElement("div");
  avatar.className = "active-avatar";
  avatar.textContent = target ? initials(target.name || target.business) : "PD";
  const copy = document.createElement("div");
  copy.className = "active-copy";
  const primary = document.createElement("strong");
  primary.textContent = target ? (target.name || target.business || target.phone) : "Ready when you are";
  const secondary = document.createElement("span");
  secondary.textContent = target
    ? [target.business, target.phone].filter(Boolean).join(" · ")
    : "Start to connect computer audio and begin dialing.";
  copy.append(primary, secondary);
  activeCall.append(avatar, copy);

  byId("startButton").disabled = state.running;
  byId("pauseButton").disabled = !state.running;
  byId("pauseButton").textContent = state.paused ? "Resume" : "Pause";
  byId("hangupButton").disabled = !active;
  byId("skipVoicemailButton").disabled = !active && !(state.in_flight?.length);
  byId("stopButton").disabled = !state.running;
  const caller = state.caller_ids?.[0];
  byId("callerIdLine").querySelector("span").textContent = caller || "Not connected";
  renderCallMonitor();

  const outcomeLead = pending || active;
  const outcomeDisabled = !outcomeLead || outcomeSubmitting;
  byId("outcomeCallButton").disabled = outcomeDisabled;
  byId("outcomeBookedButton").disabled = outcomeDisabled;
  byId("outcomeDisqualifiedButton").disabled = outcomeDisabled;
  setText("outcomeRowLabel", outcomeLead ? `Outcome · ${outcomeLead.name || outcomeLead.phone}` : "Outcome");
}

function formatMinutes(totalSeconds) {
  const minutes = Math.round((totalSeconds || 0) / 60);
  return `${minutes}m`;
}

function dayLabel(dateStr) {
  const date = new Date(`${dateStr}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return dateStr.slice(5);
  return date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
}

function buildMetricsLineChart(series) {
  const container = byId("metricsLineChart");
  const width = 620;
  const height = 190;
  const left = 36;
  const right = 10;
  const top = 12;
  const bottom = 28;
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;
  const maxValue = Math.max(1, ...series.map((day) => Math.max(day.dials || 0, day.connected || 0)));
  const xFor = (index) => left + index * plotWidth / Math.max(1, series.length - 1);
  const yFor = (value) => top + plotHeight - (value / maxValue) * plotHeight;
  const svgParts = [];

  for (let step = 0; step <= 2; step += 1) {
    const value = Math.round(maxValue * (2 - step) / 2);
    const y = top + plotHeight * step / 2;
    svgParts.push(`<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" class="line-chart-gridline" />`);
    svgParts.push(`<text x="${left - 8}" y="${y + 3}" class="line-chart-axis-label">${value}</text>`);
  }

  for (const metric of ["dials", "connected"]) {
    const points = series.map((day, index) => `${xFor(index)},${yFor(day[metric] || 0)}`);
    svgParts.push(`<polyline points="${points.join(" ")}" class="line-series line-series-${metric}" />`);
    series.forEach((day, index) => {
      svgParts.push(`<circle cx="${xFor(index)}" cy="${yFor(day[metric] || 0)}" r="3" class="line-point line-point-${metric}"><title>${dayLabel(day.date)}: ${day[metric] || 0} ${metric}</title></circle>`);
    });
  }

  series.forEach((day, index) => {
    svgParts.push(`<text x="${xFor(index)}" y="${height - 7}" class="line-chart-day-label">${dayLabel(day.date)}</text>`);
  });
  container.innerHTML = `<svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none" role="presentation">${svgParts.join("")}</svg>`;
}

function pieSlicePath(cx, cy, radius, startAngle, endAngle) {
  const startRadians = startAngle * Math.PI / 180;
  const endRadians = endAngle * Math.PI / 180;
  const startX = cx + radius * Math.cos(startRadians);
  const startY = cy + radius * Math.sin(startRadians);
  const endX = cx + radius * Math.cos(endRadians);
  const endY = cy + radius * Math.sin(endRadians);
  const largeArc = endAngle - startAngle > 180 ? 1 : 0;
  return `M${cx},${cy} L${startX},${startY} A${radius},${radius} 0 ${largeArc} 1 ${endX},${endY} Z`;
}

function buildStatusPieChart(leads) {
  const chart = byId("statusPieChart");
  const legend = byId("statusPieLegend");
  const statuses = ["new", "call", "booked", "disqualified"];
  const counts = Object.fromEntries(statuses.map((status) => [status, 0]));
  for (const lead of leads) {
    if (Object.hasOwn(counts, lead.status)) counts[lead.status] += 1;
  }
  const total = leads.length;
  const center = 76;
  const radius = 66;
  let angle = -90;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No prospects</text>`);
  } else {
    const visible = statuses.filter((status) => counts[status] > 0);
    if (visible.length === 1) {
      slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${STATUS_COLOR_VARS[visible[0]]})"><title>${STATUS_LABELS[visible[0]]}: ${counts[visible[0]]}</title></circle>`);
    } else {
      for (const status of visible) {
        const nextAngle = angle + counts[status] / total * 360;
        slices.push(`<path d="${pieSlicePath(center, center, radius, angle, nextAngle)}" fill="var(${STATUS_COLOR_VARS[status]})" stroke="var(--paper)" stroke-width="2"><title>${STATUS_LABELS[status]}: ${counts[status]}</title></path>`);
        angle = nextAngle;
      }
    }
  }

  chart.setAttribute("aria-label", `Prospects by status, ${total} total`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...statuses.map((status) => {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch status-pie-${status}`;
    const label = document.createElement("span");
    label.textContent = STATUS_LABELS[status];
    const value = document.createElement("strong");
    const percent = total ? Math.round(counts[status] / total * 100) : 0;
    value.textContent = `${counts[status]} · ${percent}%`;
    item.append(swatch, label, value);
    return item;
  }));
}

function buildConnectionPieChart(allTime) {
  const chart = byId("connectionPieChart");
  const legend = byId("connectionPieLegend");
  const total = Math.max(0, Number(allTime.dials) || 0);
  const connected = Math.min(total, Math.max(0, Number(allTime.connected) || 0));
  const notConnected = total - connected;
  const center = 76;
  const radius = 66;
  const slices = [];

  if (!total) {
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(--line-strong)" />`);
    slices.push(`<text x="${center}" y="${center + 4}" class="pie-empty-label">No dials</text>`);
  } else if (!connected || !notConnected) {
    const color = connected ? "--success" : "--amber";
    const label = connected ? "Connected" : "Not connected";
    slices.push(`<circle cx="${center}" cy="${center}" r="${radius}" fill="var(${color})"><title>${label}: ${total}</title></circle>`);
  } else {
    const splitAngle = -90 + connected / total * 360;
    slices.push(`<path d="${pieSlicePath(center, center, radius, -90, splitAngle)}" fill="var(--success)" stroke="var(--paper)" stroke-width="2"><title>Connected: ${connected}</title></path>`);
    slices.push(`<path d="${pieSlicePath(center, center, radius, splitAngle, 270)}" fill="var(--amber)" stroke="var(--paper)" stroke-width="2"><title>Not connected: ${notConnected}</title></path>`);
  }

  chart.setAttribute("aria-label", `Dial outcomes: ${connected} connected and ${notConnected} not connected`);
  chart.innerHTML = `<svg viewBox="0 0 152 152" role="presentation">${slices.join("")}</svg>`;
  legend.replaceChildren(...[
    { label: "Connected", count: connected, className: "connection-connected" },
    { label: "Not connected", count: notConnected, className: "connection-unconnected" },
  ].map((item) => {
    const row = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = `status-pie-swatch ${item.className}`;
    const label = document.createElement("span");
    label.textContent = item.label;
    const value = document.createElement("strong");
    const percent = total ? Math.round(item.count / total * 100) : 0;
    value.textContent = `${item.count} · ${percent}%`;
    row.append(swatch, label, value);
    return row;
  }));
}

function renderMetrics() {
  const today = state.metrics?.today || {};
  const allTime = state.metrics?.all_time || {};
  const daily = state.metrics?.daily || [];
  setText("statDialsToday", String(today.dials || 0));
  setText("statDialsAll", String(allTime.dials || 0));
  setText("statConnectedToday", String(today.connected || 0));
  setText("statConnectedAll", String(allTime.connected || 0));
  setText("statBookedToday", String(today.booked || 0));
  setText("statBookedAll", String(allTime.booked || 0));
  setText("statTalkToday", formatMinutes(today.talk_seconds));
  setText("statTalkAll", formatMinutes(allTime.talk_seconds));
  buildMetricsLineChart(daily);
  buildStatusPieChart(state.leads);
  buildConnectionPieChart(allTime);
}

function setDashboardTab(name, moveFocus = false) {
  const tabs = ["performance", "prospects", "transcript", "pool"];
  dashboardTab = tabs.includes(name) ? name : "performance";
  const tabButtons = {
    performance: "performanceTabButton",
    prospects: "prospectsTabButton",
    transcript: "transcriptTabButton",
    pool: "poolTabButton",
  };
  const selectedButton = byId(tabButtons[dashboardTab]);
  for (const button of document.querySelectorAll("[data-dashboard-tab]")) {
    const selected = button === selectedButton;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  }
  for (const tab of tabs) byId(`${tab}TabPanel`).hidden = dashboardTab !== tab;
  if (dashboardTab === "prospects") renderTable();
  if (dashboardTab === "pool") renderCallerPool();
  if (dashboardTab === "transcript") renderTranscriptTab();
  if (moveFocus) selectedButton.focus();
}

function setPerformanceMode(mode) {
  performanceMode = mode === "all" ? "all" : "summary";
  byId("performanceTabPanel").dataset.mode = performanceMode;
  for (const button of document.querySelectorAll("[data-performance-mode]")) {
    const selected = button.dataset.performanceMode === performanceMode;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-pressed", String(selected));
  }
}

function render() {
  setText("totalCount", String(state.counts?.total ?? state.leads.length));
  setText("newCount", String(state.counts?.new ?? state.pool.length));
  setText("bookedCount", String(state.counts?.booked ?? 0));
  setText("prospectTabCount", String(state.counts?.total ?? state.leads.length));
  renderTable();
  renderCallerPool();
  renderTranscriptTab();
  renderDialer();
  renderMetrics();
}

async function refreshState() {
  if (pollBusy) return;
  pollBusy = true;
  try {
    const [stateResult, metricsResult] = await Promise.all([
      request("/api/state"),
      request("/api/metrics").catch(() => null),
    ]);
    Object.assign(state, stateResult);
    const activeLeadId = state.active_lead_id || null;
    if (activeLeadId && activeLeadId !== observedActiveLeadId) setDashboardTab("transcript");
    observedActiveLeadId = activeLeadId;
    if (metricsResult) state.metrics = metricsResult;
    render();
  } catch (error) {
    showToast(error.message, true);
  } finally {
    pollBusy = false;
  }
}

async function changeLeadStatus(lead, status, select) {
  select.disabled = true;
  byId("saveState").textContent = "Saving…";
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, { status });
    Object.assign(state, result.state);
    byId("saveState").textContent = "All changes saved";
    render();
    showToast(`${lead.name || lead.phone}: ${status === "call" ? "call scheduled for tomorrow" : STATUS_LABELS[status].toLowerCase()}`);
  } catch (error) {
    select.value = lead.status;
    select.disabled = false;
    byId("saveState").textContent = "Save failed";
    showToast(error.message, true);
  }
}

async function deleteSelectedProspects() {
  const ids = [...selectedLeadIds];
  if (!ids.length) return;
  const noun = ids.length === 1 ? "prospect" : "prospects";
  if (!window.confirm(`Delete ${ids.length} selected ${noun}? This cannot be undone.`)) return;

  const button = byId("deleteSelectedButton");
  button.disabled = true;
  byId("saveState").textContent = "Deleting…";
  const results = await Promise.allSettled(ids.map((id) => request(`/api/leads/${encodeURIComponent(id)}`, { method: "DELETE" })));
  try {
    Object.assign(state, await request("/api/state"));
    const failed = results.filter((result) => result.status === "rejected");
    if (failed.length === 0) {
      selectedLeadIds.clear();
      selectionAnchorId = null;
      byId("saveState").textContent = "All changes saved";
      render();
      showToast(`${ids.length} ${noun} deleted`);
    } else {
      byId("saveState").textContent = "Some deletions failed";
      render();
      showToast(`${ids.length - failed.length} deleted; ${failed.length} could not be deleted.`, true);
    }
  } catch (error) {
    byId("saveState").textContent = "Refresh failed";
    showToast(error.message, true);
  } finally {
    button.disabled = false;
  }
}

function showToast(message, isError = false) {
  const toast = byId("toast");
  toast.textContent = message;
  toast.classList.toggle("error", isError);
  toast.classList.add("visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("visible"), 3200);
}

async function openSettings() {
  try {
    const settings = await request("/api/settings");
    byId("accountSidInput").value = settings.account_sid || "";
    byId("authTokenInput").value = "";
    byId("authTokenInput").placeholder = settings.has_auth_token ? "Saved token, blank to keep it" : "Twilio Auth Token";
    byId("apiKeyInput").value = settings.api_key || "";
    byId("apiSecretInput").value = "";
    byId("apiSecretInput").placeholder = settings.has_api_secret ? "Saved secret, blank to keep it" : "Twilio API Key Secret";
    byId("twimlAppSidInput").value = settings.twiml_app_sid || "";
    byId("publicUrlInput").value = settings.public_base_url || "";
    await refreshAudioDevices();
    byId("settingsDialog").showModal();
  } catch (error) {
    showToast(error.message, true);
  }
}

function setMicLevel(percent) {
  const value = Math.max(0, Math.min(100, Math.round(percent)));
  byId("microphoneLevel").setAttribute("aria-valuenow", String(value));
  byId("microphoneLevelBar").style.transform = `scaleX(${value / 100})`;
  byId("micLevelValue").textContent = `${value}%`;
  byId("micQualityStatus").textContent = value < 3 ? "Very quiet" : value > 85 ? "Very loud" : "Input active";
}

function populateAudioSelect(select, devices, kind, storageKey) {
  const saved = localStorage.getItem(storageKey) || "default";
  const options = [new Option("System default", "default")];
  let index = 0;
  for (const device of devices) {
    if (device.kind !== kind || device.deviceId === "default") continue;
    index += 1;
    const label = device.label || `${kind === "audioinput" ? "Microphone" : "Output"} ${index}`;
    options.push(new Option(label, device.deviceId));
  }
  select.replaceChildren(...options);
  select.value = options.some((option) => option.value === saved) ? saved : "default";
  localStorage.setItem(storageKey, select.value);
}

async function refreshAudioDevices(requestPermission = false) {
  if (!navigator.mediaDevices?.enumerateDevices) {
    throw new Error("This browser does not support audio device selection.");
  }
  let permissionStream;
  try {
    if (requestPermission) permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const devices = await navigator.mediaDevices.enumerateDevices();
    populateAudioSelect(byId("audioInputSelect"), devices, "audioinput", audioInputStorageKey);
    populateAudioSelect(byId("audioOutputSelect"), devices, "audiooutput", audioOutputStorageKey);
  } finally {
    permissionStream?.getTracks().forEach((track) => track.stop());
  }
}

async function routeTestAudio(audioElement) {
  const outputId = byId("audioOutputSelect").value || "default";
  audioElement.volume = Number(byId("testVolumeInput").value) / 100;
  if (typeof audioElement.setSinkId === "function") {
    await audioElement.setSinkId(outputId);
  } else if (outputId !== "default") {
    throw new Error("This browser cannot route audio to a selected output. Try a current version of Chrome or Edge.");
  }
}

async function applyVoiceAudioDevices() {
  if (!voiceDevice?.audio) return;
  const inputId = byId("audioInputSelect").value || "default";
  const outputId = byId("audioOutputSelect").value || "default";
  if (inputId === "default" && voiceDevice.audio.inputDevice) {
    await voiceDevice.audio.unsetInputDevice();
  } else if (inputId !== "default" && voiceDevice.audio.availableInputDevices?.has(inputId)) {
    await voiceDevice.audio.setInputDevice(inputId);
  } else if (inputId !== "default") {
    throw new Error("The selected microphone is unavailable in this browser.");
  }
  if (voiceDevice.audio.isOutputSelectionSupported &&
      (outputId === "default" || voiceDevice.audio.availableOutputDevices?.has(outputId))) {
    await voiceDevice.audio.speakerDevices.set(outputId);
  } else if (outputId !== "default") {
    throw new Error("This browser cannot route call audio to a selected output device.");
  }
}

async function createVoiceDevice() {
  if (voiceDevice) return voiceDevice;
  if (!window.Twilio?.Device) {
    throw new Error("The Twilio Voice SDK did not load. Check your internet connection and reload the app.");
  }
  const { token } = await request("/api/voice-token");
  voiceDevice = new window.Twilio.Device(token, {
    codecPreferences: ["opus", "pcmu"],
    closeProtection: true,
    logLevel: 2,
  });
  voiceDevice.on("error", (error) => showToast(error.message || "Twilio audio device error.", true));
  voiceDevice.on("tokenWillExpire", async () => {
    try {
      const refreshed = await request("/api/voice-token");
      voiceDevice?.updateToken(refreshed.token);
    } catch (error) {
      showToast(error.message, true);
    }
  });
  voiceDevice.audio.on("deviceChange", () => refreshAudioDevices().catch((error) => showToast(error.message, true)));
  voiceDevice.audio.on("inputVolume", (volume) => setMicLevel(volume * 100));
  await applyVoiceAudioDevices();
  return voiceDevice;
}

async function startMicrophoneTest() {
  if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
    showToast("Microphone recording is not supported in this browser.", true);
    return;
  }
  byId("startMicTest").disabled = true;
  try {
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    micTestStream = await navigator.mediaDevices.getUserMedia({ audio });
    await refreshAudioDevices();
    micTestContext = new (window.AudioContext || window.webkitAudioContext)();
    await micTestContext.resume();
    const source = micTestContext.createMediaStreamSource(micTestStream);
    const analyser = micTestContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    micPeakLevel = 0;
    micClippingFrames = 0;
    const samples = new Float32Array(analyser.fftSize);
    const measure = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      let peak = 0;
      for (const sample of samples) {
        sum += sample * sample;
        peak = Math.max(peak, Math.abs(sample));
      }
      micPeakLevel = Math.max(micPeakLevel, peak);
      if (peak >= 0.98) micClippingFrames += 1;
      setMicLevel(Math.sqrt(sum / samples.length) * 400);
      micTestFrame = requestAnimationFrame(measure);
    };
    measure();
    micTestChunks = [];
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    micTestRecorder = new MediaRecorder(micTestStream, mimeType ? { mimeType } : undefined);
    micTestRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) micTestChunks.push(event.data);
    });
    micTestRecorder.start();
    byId("audioTestStatus").textContent = "Speak now. The level meter is live and your sample is being recorded locally.";
    byId("stopMicTest").disabled = false;
  } catch (error) {
    cancelAnimationFrame(micTestFrame);
    micTestStream?.getTracks().forEach((track) => track.stop());
    micTestStream = null;
    await micTestContext?.close();
    micTestContext = null;
    setMicLevel(0);
    byId("startMicTest").disabled = false;
    showToast(error.message || "Could not access the selected microphone.", true);
  }
}

async function stopMicrophoneTest() {
  const recorder = micTestRecorder;
  if (!recorder || recorder.state === "inactive") return;
  byId("stopMicTest").disabled = true;
  await new Promise((resolve) => {
    recorder.addEventListener("stop", resolve, { once: true });
    recorder.stop();
  });
  cancelAnimationFrame(micTestFrame);
  micTestStream?.getTracks().forEach((track) => track.stop());
  micTestStream = null;
  await micTestContext?.close();
  micTestContext = null;
  micTestRecorder = null;
  setMicLevel(0);
  byId("startMicTest").disabled = false;
  const sample = new Blob(micTestChunks, { type: recorder.mimeType || "audio/webm" });
  if (!sample.size) {
    byId("audioTestStatus").textContent = "No audio was recorded. Check microphone permission and try again.";
    return;
  }
  if (micPlaybackUrl) URL.revokeObjectURL(micPlaybackUrl);
  micPlaybackUrl = URL.createObjectURL(sample);
  const playback = byId("audioPlayback");
  playback.src = micPlaybackUrl;
  playback.hidden = false;
  await routeTestAudio(playback);
  const quality = micPeakLevel < 0.025 ? "The mic level is very low" : micClippingFrames > 2 ? "The mic is clipping" : "Mic level looks healthy";
  byId("audioTestStatus").textContent = `${quality}. Play the local sample to check clarity and headphone volume.`;
}

async function testAudioOutput() {
  let context;
  let oscillator;
  const playback = byId("outputTestPlayback");
  try {
    context = new (window.AudioContext || window.webkitAudioContext)();
    await context.resume();
    const destination = context.createMediaStreamDestination();
    playback.srcObject = destination.stream;
    await routeTestAudio(playback);
    await playback.play();
    oscillator = context.createOscillator();
    const gain = context.createGain();
    const now = context.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.04);
    gain.gain.setValueAtTime(0.18, now + 0.25);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.32);
    gain.gain.setValueAtTime(0.0001, now + 0.36);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.4);
    gain.gain.setValueAtTime(0.18, now + 0.6);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.68);
    oscillator.frequency.setValueAtTime(440, now);
    oscillator.frequency.setValueAtTime(660, now + 0.36);
    oscillator.connect(gain).connect(destination);
    oscillator.start(now);
    oscillator.stop(now + 0.72);
    byId("audioTestStatus").textContent = "Playing a two-tone output test through the selected device.";
    window.setTimeout(async () => {
      playback.pause();
      playback.srcObject = null;
      await context.close();
      byId("audioTestStatus").textContent = "Output test complete.";
    }, 800);
  } catch (error) {
    oscillator?.stop();
    playback.pause();
    playback.srcObject = null;
    await context?.close();
    showToast(error.message || "Could not play the output test.", true);
  }
}

async function importCsv(file) {
  if (!file) return;
  const button = byId("importButton");
  button.disabled = true;
  button.textContent = "Importing…";
  try {
    const buffer = await file.arrayBuffer();
    const result = await request("/api/import", {
      method: "POST",
      headers: { "Content-Type": "text/csv" },
      body: buffer,
    });
    Object.assign(state, result.state);
    render();
    const imported = result.import;
    showToast(`${imported.added} prospect${imported.added === 1 ? "" : "s"} added${imported.duplicates ? ` · ${imported.duplicates} duplicate${imported.duplicates === 1 ? "" : "s"} skipped` : ""}`);
  } catch (error) {
    console.error("CSV import failed:", error);
    showToast(error?.message || "Import failed. Check the console for details.", true);
  } finally {
    button.disabled = false;
    button.innerHTML = '<span class="button-symbol" aria-hidden="true">↑</span>Import CSV';
    byId("csvInput").value = "";
  }
}

async function startDialing() {
  byId("startButton").disabled = true;
  let sessionStarted = false;
  try {
    const session = await postJson("/api/start");
    sessionStarted = true;
    const { client_call_token: clientCallToken, ...sessionState } = session;
    if (!clientCallToken) throw new Error("The browser call session could not be created.");
    Object.assign(state, sessionState);
    render();
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    const permissionStream = await navigator.mediaDevices.getUserMedia({ audio });
    permissionStream.getTracks().forEach((track) => track.stop());
    await refreshAudioDevices();
    const device = await createVoiceDevice();
    await applyVoiceAudioDevices();
    voiceCall = await device.connect({
      params: { CallToken: clientCallToken },
      rtcConstraints: { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } },
    });
    voiceCall.on("disconnect", () => {
      voiceCall = null;
      drawProspectWaveform(0);
      if (voiceDevice?.audio?.unsetInputDevice) {
        voiceDevice.audio.unsetInputDevice().catch(() => {});
      }
    });
    voiceCall.on("volume", (_inputVolume, outputVolume) => drawProspectWaveform(outputVolume));
    voiceCall.on("error", (error) => showToast(error.message || "Browser call failed.", true));
    Object.assign(state, await request("/api/state"));
    render();
  } catch (error) {
    if (sessionStarted) await postJson("/api/stop").catch(() => {});
    voiceDevice?.destroy();
    voiceDevice = null;
    voiceCall = null;
    drawProspectWaveform(0);
    Object.assign(state, await request("/api/state").catch(() => ({})));
    render();
    showToast(error.message, true);
    if (!sessionStarted) openSettings();
  } finally {
    byId("startButton").disabled = state.running;
  }
}

for (const tabButton of document.querySelectorAll("[data-dashboard-tab]")) {
  tabButton.addEventListener("click", () => setDashboardTab(tabButton.dataset.dashboardTab));
  tabButton.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const tabs = ["performance", "prospects", "transcript", "pool"];
    const index = tabs.indexOf(tabButton.dataset.dashboardTab);
    const next = event.key === "Home" ? 0
      : event.key === "End" ? tabs.length - 1
        : (index + (event.key === "ArrowRight" ? 1 : tabs.length - 1)) % tabs.length;
    const name = tabs[next];
    setDashboardTab(name, true);
  });
}
for (const modeButton of document.querySelectorAll("[data-performance-mode]")) {
  modeButton.addEventListener("click", () => setPerformanceMode(modeButton.dataset.performanceMode));
}
byId("closeTranscript").addEventListener("click", () => byId("transcriptDialog").close());
byId("transcriptDialog").addEventListener("click", (event) => {
  if (event.target === byId("transcriptDialog")) byId("transcriptDialog").close();
});
byId("settingsButton").addEventListener("click", openSettings);
byId("settingsDialog").addEventListener("close", () => {
  if (micTestRecorder?.state === "recording") {
    stopMicrophoneTest().catch((error) => showToast(error.message, true));
  }
});
byId("closeSettings").addEventListener("click", () => byId("settingsDialog").close());
byId("cancelSettings").addEventListener("click", () => byId("settingsDialog").close());
byId("settingsForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const submit = byId("settingsForm").querySelector("[type=submit]");
  submit.disabled = true;
  try {
    const settings = await postJson("/api/settings", {
      account_sid: byId("accountSidInput").value,
      auth_token: byId("authTokenInput").value,
      api_key: byId("apiKeyInput").value,
      api_secret: byId("apiSecretInput").value,
      twiml_app_sid: byId("twimlAppSidInput").value,
      public_base_url: byId("publicUrlInput").value,
    });
    byId("authTokenInput").value = "";
    byId("apiSecretInput").value = "";
    byId("settingsDialog").close();
    showToast("Dialer settings saved");
  } catch (error) {
    showToast(error.message, true);
  } finally {
    submit.disabled = false;
  }
});

byId("importButton").addEventListener("click", () => byId("csvInput").click());
byId("deleteSelectedButton").addEventListener("click", deleteSelectedProspects);
byId("csvInput").addEventListener("change", (event) => {
  const file = event.target.files[0];
  if (!file) {
    console.warn("CSV file picker closed with no file selected.");
    return;
  }
  console.log(`CSV file selected: ${file.name} (${file.size} bytes, type "${file.type}")`);
  importCsv(file);
});
document.querySelectorAll("[data-import]").forEach((button) => button.addEventListener("click", () => byId("csvInput").click()));
byId("searchInput").addEventListener("input", renderTable);
byId("statusFilter").addEventListener("change", renderTable);
byId("startButton").addEventListener("click", startDialing);
byId("pauseButton").addEventListener("click", async () => {
  try { Object.assign(state, await postJson("/api/pause")); render(); }
  catch (error) { showToast(error.message, true); }
});
byId("stopButton").addEventListener("click", async () => {
  try {
    Object.assign(state, await postJson("/api/stop"));
    voiceDevice?.destroy();
    voiceDevice = null;
    voiceCall = null;
    render();
  }
  catch (error) { showToast(error.message, true); }
});
byId("hangupButton").addEventListener("click", async () => {
  try { Object.assign(state, await postJson("/api/hangup")); render(); }
  catch (error) { showToast(error.message, true); }
});
byId("skipVoicemailButton").addEventListener("click", async () => {
  try {
    Object.assign(state, await postJson("/api/skip"));
    showToast("Prospect skipped and marked for later");
    render();
  } catch (error) {
    showToast(error.message, true);
  }
});
for (const selector of [byId("dialerTimezoneFilter"), byId("poolTimezoneFilter")]) {
  selector.addEventListener("change", (event) => selectTimezone(event.target.value));
}
async function submitOutcome(status) {
  const lead = state.pending_outcome || state.active_lead;
  if (!lead || outcomeSubmitting) return;
  outcomeSubmitting = true;
  render();
  try {
    const result = await postJson(`/api/leads/${encodeURIComponent(lead.id)}/status`, { status });
    Object.assign(state, result.state);
    showToast(`${lead.name || lead.phone}: ${status === "call" ? "call scheduled for tomorrow" : STATUS_LABELS[status].toLowerCase()}`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    outcomeSubmitting = false;
    render();
  }
}
byId("outcomeCallButton").addEventListener("click", () => submitOutcome("call"));
byId("outcomeBookedButton").addEventListener("click", () => submitOutcome("booked"));
byId("outcomeDisqualifiedButton").addEventListener("click", () => submitOutcome("disqualified"));
byId("refreshAudioDevices").addEventListener("click", async () => {
  try {
    await refreshAudioDevices(true);
    await applyVoiceAudioDevices();
    showToast("Audio devices refreshed");
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("audioInputSelect").addEventListener("change", async (event) => {
  localStorage.setItem(audioInputStorageKey, event.target.value);
  try {
    if (micTestRecorder?.state === "recording") await stopMicrophoneTest();
    await applyVoiceAudioDevices();
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("audioOutputSelect").addEventListener("change", async (event) => {
  localStorage.setItem(audioOutputStorageKey, event.target.value);
  try {
    await applyVoiceAudioDevices();
    await routeTestAudio(byId("audioPlayback"));
  } catch (error) {
    showToast(error.message, true);
  }
});
byId("startMicTest").addEventListener("click", startMicrophoneTest);
byId("stopMicTest").addEventListener("click", () => stopMicrophoneTest().catch((error) => showToast(error.message, true)));
byId("outputTestButton").addEventListener("click", testAudioOutput);
byId("testVolumeInput").addEventListener("input", (event) => {
  const value = Number(event.target.value);
  byId("testVolumeValue").textContent = `${value}%`;
  byId("audioPlayback").volume = value / 100;
  byId("outputTestPlayback").volume = value / 100;
});
if (navigator.mediaDevices?.addEventListener) {
  navigator.mediaDevices.addEventListener("devicechange", () => refreshAudioDevices().catch(() => {}));
}
drawProspectWaveform(0);
refreshState();
request("/api/settings").then((settings) => {
  if (!settings.account_sid || !settings.has_auth_token || !settings.api_key || !settings.has_api_secret || !settings.twiml_app_sid || !settings.public_base_url) {
    showToast("Complete your Twilio Voice credentials and callback URL in Settings to start dialing.");
  }
}).catch(() => {});
setInterval(refreshState, 1500);