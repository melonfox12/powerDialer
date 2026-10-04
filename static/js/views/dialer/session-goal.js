import { arcadeSensory } from "../../features/arcade/controller/index.js";
import { S, state } from "../../store/state.js";
import { byId, setText } from "../../utils/format.js";
import { showToast } from "../../utils/notify.js";

export function renderSessionMomentum() {
  const stats = state.session_stats || {};
  const goal = Number(stats.goal || state.settings?.session_goal || 20);
  const conversations = Number(stats.conversations || 0);
  setText("sessionGoalLabel", `${conversations} / ${goal} conversations`);
  const progress = byId("sessionGoalTrack");
  progress.setAttribute("aria-valuemax", String(goal));
  progress.setAttribute("aria-valuenow", String(Math.min(conversations, goal)));
  byId("sessionGoalProgress").style.width = `${goal ? Math.min(100, conversations / goal * 100) : 0}%`;
  const streak = Number(stats.current_streak || 0);
  const streakElement = byId("sessionStreak");
  streakElement.hidden = streak < 2;
  streakElement.textContent = streak >= 2 ? `${streak} connects in the last 10 min` : "";
  const sessionId = stats.id || "";
  if (sessionId !== S.celebratedSessionId) {
    S.celebratedSessionId = sessionId;
    S.goalCelebrated = localStorage.getItem(`prospect-desk-goal-${sessionId}`) === "shown";
    S.previousSessionConversations = conversations;
    S.previousMeetings = Number(stats.meetings_booked || 0);
    S.dismissedBreakForSession = null;
    S.halfwaySessionId = "";
    byId("sessionHalfway").hidden = true;
  } else if (conversations > S.previousSessionConversations) {
    const label = byId("sessionGoalLabel");
    label.classList.remove("goal-pulse");
    void label.offsetWidth;
    label.classList.add("goal-pulse");
  }
  if (sessionId && S.halfwaySessionId !== sessionId && goal > 0 && conversations >= goal / 2 && conversations < goal) {
    S.halfwaySessionId = sessionId;
    const halfway = byId("sessionHalfway");
    halfway.hidden = false;
    clearTimeout(S.halfwayTimer);
    S.halfwayTimer = setTimeout(() => { halfway.hidden = true; }, 4000);
  }
  if (conversations >= goal && !S.goalCelebrated) {
    S.goalCelebrated = true;
    localStorage.setItem(`prospect-desk-goal-${sessionId}`, "shown");
    showToast("Session goal reached — great work!");
    if (arcadeSensory.preferences.enabled) arcadeSensory.burstParticles();
  }
  if (Number(stats.meetings_booked || 0) > S.previousMeetings) byId("statBookedToday").classList.add("meeting-highlight");
  S.previousMeetings = Number(stats.meetings_booked || 0);
  S.previousSessionConversations = conversations;
  const nudgeMinutes = Number(state.settings?.break_nudge_minutes || 90);
  const elapsed = (Date.now() - Date.parse(stats.started_at || Date.now())) / 60000;
  const showNudge = state.running && elapsed >= nudgeMinutes && S.dismissedBreakForSession !== sessionId;
  byId("breakNudge").hidden = !showNudge;
}

export function bindSessionGoal() {
  byId("breakPauseButton").addEventListener("click", () => {
    byId("pauseButton").click();
    byId("breakNudge").hidden = true;
  });
  byId("breakDismissButton").addEventListener("click", () => {
    S.dismissedBreakForSession = state.session_stats?.id || null;
    byId("breakNudge").hidden = true;
  });
}
