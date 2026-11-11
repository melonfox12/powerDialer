import { stageEffects } from "./effects.js";
import { S, state } from "../../_core/state.js";
import { dialerEls, setDialerText } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";

export function renderSessionMomentum() {
  const stats = state.session_stats || {};
  const goal = Number(stats.goal || state.settings?.session_goal || 20);
  const conversations = Number(stats.conversations || 0);
  setDialerText("sessionGoalLabel", `${conversations} / ${goal} conversations`);
  for (const progress of dialerEls("sessionGoalTrack")) {
    progress.setAttribute("aria-valuemax", String(goal));
    progress.setAttribute("aria-valuenow", String(Math.min(conversations, goal)));
  }
  const widthPct = `${goal ? Math.min(100, conversations / goal * 100) : 0}%`;
  for (const span of dialerEls("sessionGoalProgress")) span.style.width = widthPct;
  const streak = Number(stats.current_streak || 0);
  const streakElements = dialerEls("sessionStreak");
  for (const streakElement of streakElements) {
    streakElement.hidden = streak < 2;
    streakElement.textContent = streak >= 2 ? `${streak} connects in the last 10 min` : "";
  }
  const sessionId = stats.id || "";
  if (sessionId !== S.celebratedSessionId) {
    S.celebratedSessionId = sessionId;
    S.goalCelebrated = localStorage.getItem(`prospect-desk-goal-${sessionId}`) === "shown";
    S.previousSessionConversations = conversations;
    S.previousMeetings = Number(stats.meetings_booked || 0);
    S.dismissedBreakForSession = null;
    S.halfwaySessionId = "";
    for (const h of dialerEls("sessionHalfway")) h.hidden = true;
  } else if (conversations > S.previousSessionConversations) {
    for (const label of dialerEls("sessionGoalLabel")) {
      label.classList.remove("goal-pulse");
      void label.offsetWidth;
      label.classList.add("goal-pulse");
    }
  }
  if (sessionId && S.halfwaySessionId !== sessionId && goal > 0 && conversations >= goal / 2 && conversations < goal) {
    S.halfwaySessionId = sessionId;
    for (const halfway of dialerEls("sessionHalfway")) {
      halfway.hidden = false;
    }
    clearTimeout(S.halfwayTimer);
    S.halfwayTimer = setTimeout(() => {
      for (const halfway of dialerEls("sessionHalfway")) halfway.hidden = true;
    }, 4000);
  }
  if (conversations >= goal && !S.goalCelebrated) {
    S.goalCelebrated = true;
    localStorage.setItem(`prospect-desk-goal-${sessionId}`, "shown");
    showToast("Session goal reached — great work!");
    stageEffects.goalReached();
  }
  if (Number(stats.meetings_booked || 0) > S.previousMeetings) {
    for (const label of dialerEls("sessionGoalLabel")) {
      label.classList.add("meeting-highlight");
      setTimeout(() => label.classList.remove("meeting-highlight"), 1200);
    }
  }
  S.previousMeetings = Number(stats.meetings_booked || 0);
  S.previousSessionConversations = conversations;
  const nudgeMinutes = Number(state.settings?.break_nudge_minutes || 90);
  const elapsed = (Date.now() - Date.parse(stats.started_at || Date.now())) / 60000;
  const showNudge = state.running && elapsed >= nudgeMinutes && S.dismissedBreakForSession !== sessionId;
  for (const nudge of dialerEls("breakNudge")) nudge.hidden = !showNudge;
}

export function bindSessionGoal() {
  for (const btn of dialerEls("breakDismissButton")) {
    btn.addEventListener("click", () => {
      S.dismissedBreakForSession = state.session_stats?.id || null;
      for (const nudge of dialerEls("breakNudge")) nudge.hidden = true;
    });
  }
}
