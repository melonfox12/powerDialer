import { byId } from "../../_core/format.js";
import { transcriptTimestamp } from "../../_core/transcript.js";
import { state } from "../../_core/state.js";

function mergedTranscriptEntries() {
  const liveTranscript = state.live_transcript || {};
  const lead = state.active_lead || state.pending_outcome
    || state.leads.find((item) => item.id === liveTranscript.lead_id) || null;
  const partials = lead && liveTranscript.lead_id === lead.id ? liveTranscript.partials || [] : [];
  const liveLines = lead && liveTranscript.lead_id === lead.id ? liveTranscript.lines || [] : [];
  const merged = new Map();
  for (const entry of [...(lead?.transcript || []), ...liveLines, ...partials]) {
    const key = entry.id || `${entry.timestamp || ""}|${entry.speaker || ""}|${entry.text || ""}`;
    merged.set(key, entry);
  }
  return [...merged.values()].sort(
    (left, right) => new Date(left.timestamp) - new Date(right.timestamp),
  );
}

function speakerSide(speaker) {
  const value = String(speaker || "").toLowerCase();
  if (value.includes("prospect") || value.includes("customer")) return "prospect";
  return "agent";
}

function bubbleFor(entry, animate) {
  const side = speakerSide(entry.speaker);
  const bubble = document.createElement("article");
  bubble.className = `ai-chat-bubble ai-chat-bubble--${side}`;
  if (animate) bubble.classList.add("is-entering");
  const text = document.createElement("p");
  text.textContent = entry.text || "";
  const meta = document.createElement("footer");
  const time = document.createElement("time");
  time.dateTime = entry.timestamp || "";
  time.textContent = transcriptTimestamp(entry.timestamp);
  meta.append(side === "prospect" ? "Prospect" : "Agent", " · ", time);
  bubble.append(text, meta);
  if (animate) {
    requestAnimationFrame(() => bubble.classList.remove("is-entering"));
  }
  return bubble;
}

let renderedKeys = [];

export function renderChatTranscript() {
  const thread = byId("aiDialerAgent-chatTranscript");
  if (!thread) return;
  const entries = mergedTranscriptEntries();
  if (!entries.length) {
    if (renderedKeys.length) {
      renderedKeys = [];
      thread.replaceChildren();
    }
    if (!thread.querySelector(".transcript-empty")) {
      const empty = document.createElement("p");
      empty.className = "transcript-empty";
      empty.textContent = "Conversation appears here as agent and prospect speak.";
      thread.replaceChildren(empty);
    }
    return;
  }
  thread.querySelector(".transcript-empty")?.remove();
  const nextKeys = entries.map((entry) => entry.id || `${entry.timestamp}|${entry.speaker}|${entry.text}`);
  const shouldFollow = thread.scrollHeight - thread.scrollTop - thread.clientHeight <= 48;
  const grewBy = Math.max(0, nextKeys.length - renderedKeys.length);
  if (nextKeys.length < renderedKeys.length || !nextKeys.every((key, index) => renderedKeys[index] === key)) {
    thread.replaceChildren();
    for (const entry of entries) thread.append(bubbleFor(entry, false));
    renderedKeys = nextKeys;
  } else if (grewBy > 0) {
    for (const entry of entries.slice(renderedKeys.length)) {
      thread.append(bubbleFor(entry, true));
    }
    renderedKeys = nextKeys;
  }
  if (shouldFollow) {
    thread.scrollTo({ top: thread.scrollHeight, behavior: grewBy > 0 ? "smooth" : "auto" });
  }
}
