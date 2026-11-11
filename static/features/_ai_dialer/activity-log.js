import { state } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { transcriptTimestamp } from "../../_core/transcript.js";

export function renderAiActivityLog() {
  const activityList = byId("aiDialerAgent-activityLog");
  const countNode = byId("aiDialerAgent-activityCount");
  if (!activityList) return;
  const activity = state.activity_log || [];
  if (countNode) {
    countNode.textContent = `${activity.length} event${activity.length === 1 ? "" : "s"}`;
  }
  activityList.replaceChildren();
  if (!activity.length) {
    const emptyRow = document.createElement("li");
    emptyRow.className = "monitor-empty";
    emptyRow.textContent = "Waiting for dialer activity.";
    activityList.append(emptyRow);
    return;
  }
  for (const entry of activity.slice(-16)) {
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
    activityList.append(row);
  }
  activityList.scrollTop = activityList.scrollHeight;
}
