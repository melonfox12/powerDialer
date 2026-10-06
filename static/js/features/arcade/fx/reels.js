import { setText } from "../../../../_core/format.js";

export const ReelsMixin = (Base) => class extends Base {
  stopTicking() {
    clearInterval(this.tickTimer);
    this.tickTimer = 0;
  }

  startSpin(leadKey) {
    if (!this.preferences.enabled) return;
    if (this.phase === "resetting") {
      this.pendingSpinKey = leadKey;
      return;
    }
    if (this.phase === "spinning" && this.activeLeadKey === leadKey) return;
    this.clearTimers();
    this.stopParticles();
    this.activeLeadKey = leadKey;
    this.phase = "spinning";
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-resetting", "is-near-miss", "is-match");
    this.viewport.querySelector("#arcadeValue").hidden = true;
    this.viewport.querySelector("#arcadeValue").textContent = "";
    setText("arcadeStatus", "Evaluating connection");
    this.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-locking", "is-near-miss");
      windowElement.classList.toggle("is-spinning", this.preferences.reels);
      this.reels[index].style.transition = "";
      this.reels[index].style.transform = "";
    });
    this.startTicking();
  }

  startTicking() {
    this.stopTicking();
    if (!this.canPlaySound()) return;
    this.tickCount = 0;
    this.tickTimer = setInterval(() => {
      this.tickCount += 1;
      this.playTick(540 + Math.min(900, this.tickCount * 12));
    }, 50);
  }

  match(lead) {
    if (!this.preferences.enabled) return;
    const key = lead?.id || this.activeLeadKey || "active-call";
    if (this.lastMatchKey === key) return;
    this.lastMatchKey = key;
    this.activeLeadKey = key;
    this.clearTimers();
    this.stopTicking();
    this.phase = "matched";
    const animationId = ++this.valueAnimation;
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-resetting", "is-near-miss");
    this.viewport.classList.add("is-match");
    setText("arcadeStatus", "Connection established");
    for (const [index, windowElement] of this.reelWindows.entries()) {
      windowElement.classList.remove("is-spinning", "is-near-miss");
      windowElement.classList.add("is-locking");
      this.schedule(() => {
        this.reels[index].style.transform = "rotateX(-72deg)";
      }, index * 150);
    }
    const rawValue = lead?.estimated_value ?? lead?.value;
    const value = Number(rawValue);
    const valueElement = this.viewport.querySelector("#arcadeValue");
    if (Number.isFinite(value) && value > 0) {
      valueElement.hidden = false;
      this.animateValue(value, valueElement, animationId);
    } else {
      valueElement.hidden = true;
      valueElement.textContent = "";
    }
    this.burstParticles();
    if (this.preferences.shake && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const panel = document.querySelector(".dialer-run-panel");
      panel.classList.remove("arcade-shake");
      void panel.offsetWidth;
      panel.classList.add("arcade-shake");
      this.schedule(() => panel.classList.remove("arcade-shake"), 420);
    }
    this.playRewardChime();
    this.vibrate([50, 20, 50, 20, 50]);
  }
};
