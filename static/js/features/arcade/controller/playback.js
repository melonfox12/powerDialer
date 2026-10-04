import { setText } from "../../../utils/format.js";

export const PlaybackMixin = (Base) => class extends Base {
  animateValue(target, element, animationId) {
    const start = performance.now();
    const duration = 650;
    const draw = (now) => {
      if (this.phase !== "matched" || animationId !== this.valueAnimation) return;
      const progress = Math.max(0, Math.min(1, (now - start) / duration));
      const eased = 1 - (1 - progress) ** 3;
      element.textContent = `+$${(target * eased).toFixed(2)} Est. Value`;
      if (progress < 1) requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  }

  reset(quiet = false) {
    if (!this.preferences.enabled) return;
    if (this.phase === "resetting") return;
    this.valueAnimation += 1;
    this.clearTimers();
    this.stopParticles();
    this.stopTicking();
    this.phase = "resetting";
    this.pendingSpinKey = null;
    this.viewport.hidden = false;
    this.viewport.classList.remove("is-match");
    this.viewport.querySelector("#arcadeValue").hidden = true;
    if (quiet) {
      this.viewport.classList.remove("is-near-miss", "is-resetting");
      setText("arcadeStatus", "Call ended");
      this.schedule(() => {
        this.viewport.classList.add("is-resetting");
        this.schedule(() => {
          this.viewport.classList.remove("is-resetting");
          this.phase = "idle";
          this.viewport.hidden = true;
        }, 270);
      }, 150);
      return;
    }
    this.viewport.classList.add("is-near-miss");
    this.viewport.classList.remove("is-resetting");
    setText("arcadeStatus", "Cycle reset · next prospect");
    this.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-spinning", "is-locking", "is-near-miss");
      if (index === 2) windowElement.classList.add("is-near-miss");
      this.reels[index].style.transition = "transform 80ms linear";
      this.reels[index].style.transform = index === 2
        ? "translateY(50%) rotateX(-216deg)"
        : "rotateX(-72deg)";
    });
    this.flashFailure();
    this.playResetTone();
    this.vibrate(250);
    this.schedule(() => {
      this.viewport.classList.add("is-resetting");
      this.schedule(() => {
        this.viewport.classList.remove("is-resetting", "is-near-miss");
        this.phase = "idle";
        if (this.pendingSpinKey) {
          const nextKey = this.pendingSpinKey;
          this.pendingSpinKey = null;
          this.startSpin(nextKey);
        } else {
          this.viewport.hidden = true;
        }
      }, 270);
    }, 150);
  }

  flashFailure() {
    const panel = document.querySelector(".dialer-run-panel");
    panel.classList.add("arcade-failure-flash");
    this.schedule(() => panel.classList.remove("arcade-failure-flash"), 150);
  }
};
