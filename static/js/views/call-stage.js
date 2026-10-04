import { playCue } from "../features/arcade/audio.js";
import { arcadeSensory } from "../features/arcade/controller.js";
import { S, state } from "../store/state.js";
import { STATUS_LABELS, byId, setText } from "../utils/format.js";
import { formatPhoneNumber } from "../utils/phone.js";

export function renderCallStage(stage, target) {
  const container = byId("callStage");
  container.hidden = stage === "idle";
  container.dataset.stage = stage;
  const fragment = document.createDocumentFragment();
  const heading = document.createElement("strong");
  const detail = document.createElement("span");
  if (stage === "connected" && target) {
    heading.textContent = state.pickup_answered_by === "voicemail" ? "VOICEMAIL" : "LIVE";
    const name = target.name || target.business || formatPhoneNumber(target.phone) || "Prospect";
    const nameElement = document.createElement("p");
    nameElement.className = "call-prospect-name";
    nameElement.textContent = name;
    fragment.append(nameElement);
    if (target.business && target.business !== name) {
      const business = document.createElement("span");
      business.className = "call-prospect-business";
      business.textContent = target.business;
      fragment.append(business);
    }
    const meta = document.createElement("span");
    meta.className = "call-prospect-meta";
    if (target.phone) {
      const phone = document.createElement("span");
      phone.textContent = formatPhoneNumber(target.phone);
      meta.append(phone);
    }
    const clock = localTimeLabel(target.timezone);
    if (clock) {
      const clockElement = document.createElement("span");
      clockElement.textContent = clock;
      meta.append(clockElement);
    }
    const timer = document.createElement("span");
    timer.id = "callTimer";
    timer.textContent = "0:00";
    meta.append(timer);
    fragment.append(meta);
    const notesEntry = Object.entries(target.fields || {}).find(([key, value]) => /notes?/i.test(key) && String(value || "").trim());
    if (notesEntry) {
      const notes = document.createElement("span");
      notes.className = "call-prospect-notes";
      notes.textContent = String(notesEntry[1]);
      fragment.append(notes);
    }
    const script = document.createElement("span");
    script.className = "call-stage-script";
    script.textContent = state.settings?.opening_script || "Introduce yourself, confirm you have the right person, then ask one clear question.";
    fragment.append(script);
    container.classList.add("call-stage-live");
    if (S.previousStage !== "connected") playCue("connect");
  } else if (stage === "paused") {
    heading.textContent = "Session paused";
    detail.textContent = "Resume when you’re ready to continue the queue.";
    container.classList.remove("call-stage-live");
  } else if (stage === "wrapup" && target) {
    heading.textContent = "Call complete";
    detail.textContent = `Choose a disposition for ${target.business || target.name || formatPhoneNumber(target.phone)}.`;
    container.classList.remove("call-stage-live");
  } else if (stage === "dialing" || stage === "ringing") {
    const calls = state.in_flight || [];
    heading.textContent = stage === "ringing" ? "Ring in progress" : "Dialing next prospect";
    detail.textContent = calls.map((call) => `${call.lead?.business || call.lead?.name || "Prospect"} · ${call.state === "ringing" ? "Ringing" : "Dialing"}`).join(" · ") || state.last_event || "Connecting to the next prospect…";
    container.classList.remove("call-stage-live");
  } else if (stage !== "idle") {
    const next = state.next_lead;
    const clock = next ? localTimeLabel(next.timezone) : "";
    const context = next && Object.entries(next.fields || {}).find(([key, value]) => /notes?/i.test(key) && value);
    detail.textContent = next
      ? `Next up: ${next.business || next.name || "Prospect"} · ${formatPhoneNumber(next.phone)} · ${clock || next.timezone || "Local time unavailable"} · ${context ? `Context: ${context[1]}` : `Status: ${STATUS_LABELS[next.status] || "New"}`}${state.skipped_outside_hours ? ` · ${state.skipped_outside_hours} skipped: outside calling hours` : ""}${state.skipped_unknown_timezone ? ` · ${state.skipped_unknown_timezone} skipped: timezone unavailable` : ""}`
      : state.skipped_outside_hours || state.skipped_unknown_timezone
        ? [
          state.skipped_outside_hours && `${state.skipped_outside_hours} skipped: outside calling hours; they’ll be dialed when local hours open.`,
          state.skipped_unknown_timezone && `${state.skipped_unknown_timezone} skipped: timezone unavailable.`,
        ].filter(Boolean).join(" ")
        : "No prospects available in this queue.";
    container.classList.remove("call-stage-live");
  }

  function localTimeLabel(timezoneName) {
    const zones = {
      Eastern: "America/New_York",
      Central: "America/Chicago",
      Mountain: "America/Denver",
      Pacific: "America/Los_Angeles",
      Alaska: "America/Anchorage",
      Hawaii: "Pacific/Honolulu",
    };
    const zone = zones[timezoneName] || timezoneName;
    try {
      const timeText = new Intl.DateTimeFormat([], { hour: "numeric", minute: "2-digit", timeZone: zone }).format(new Date());
      return `${timeText} ${timezoneName}`;
    } catch (error) {
      if (error instanceof RangeError) return "";
      throw error;
    }
  }
  if (stage === "connected") fragment.prepend(heading);
  else if (stage !== "idle") fragment.append(heading, detail);
  container.replaceChildren(fragment);
  stopCallTimer();
  if (stage === "connected") {
    const started = state.active_call_started_at ? Date.parse(state.active_call_started_at) : Date.now();
    startCallTimer(Number.isFinite(started) ? started : Date.now());
  }
  if (stage !== S.previousStage && stage !== "idle") {
    setText("stageAnnouncer", stage === "connected"
      ? (state.pickup_answered_by === "voicemail" ? "Voicemail picked up. Stay on the line or skip." : "Prospect picked up. Stay on the line or skip.")
      : stage === "wrapup" ? "Call ended. Choose a disposition." : stage === "paused" ? "Dialing session paused." : stage === "ringing" ? "Prospect line is ringing." : "Dialing next prospect.");
    container.classList.remove("stage-enter");
    void container.offsetWidth;
    container.classList.add("stage-enter");
  }
  if (stage === "idle" && S.previousStage !== "idle") setText("stageAnnouncer", "Dialing session stopped.");
  if (stage === "connected" && S.previousStage !== "connected") S.connectedAt = Date.now();
  if (stage === "connected" && S.previousStage !== "connected") arcadeSensory.match(state.active_lead);
  if (S.previousStage === "connected" && stage === "wrapup") arcadeSensory.reset(true);
  if (S.previousStage === "ringing" && stage === "dialing") arcadeSensory.reset();
  if ((stage === "idle" || stage === "paused") && stage !== S.previousStage) arcadeSensory.stop();
  if (stage === "dialing" || stage === "ringing") {
    const call = (state.in_flight || []).find((item) => ["creating", "ringing"].includes(item.state));
    const lead = call?.lead || state.next_lead;
    arcadeSensory.startSpin(lead?.id || call?.lead_id || "dialing");
  }
  if (stage !== "connected") S.connectedAt = null;
  S.previousStage = stage;
}

export function stopCallTimer() {
  clearInterval(S.callTimerId);
  S.callTimerId = null;
}

export function startCallTimer(startedMs) {
  stopCallTimer();
  const node = document.getElementById("callTimer");
  if (!node) return;
  const tick = () => {
    if (!node.isConnected || (state.stage || "idle") !== "connected") {
      stopCallTimer();
      return;
    }
    const seconds = Math.max(0, Math.floor((Date.now() - startedMs) / 1000));
    node.textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
  };
  tick();
  S.callTimerId = setInterval(tick, 1000);
}
