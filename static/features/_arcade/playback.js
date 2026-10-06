import { setText } from "../../_core/format.js";

export function animateValue(arcade, target, element, animationId) {
    const start = performance.now();
    const duration = 650;
    const draw = (now) => {
      if (arcade.phase !== "matched" || animationId !== arcade.valueAnimation) return;
      const progress = Math.max(0, Math.min(1, (now - start) / duration));
      const eased = 1 - (1 - progress) ** 3;
      element.textContent = `+$${(target * eased).toFixed(2)} Est. Value`;
      if (progress < 1) requestAnimationFrame(draw);
    };
    requestAnimationFrame(draw);
  }

export function reset(arcade, quiet = false) {
    if (!arcade.preferences.enabled) return;
    if (arcade.phase === "resetting") return;
    arcade.valueAnimation += 1;
    arcade.clearTimers();
    arcade.stopParticles();
    arcade.stopTicking();
    arcade.phase = "resetting";
    arcade.pendingSpinKey = null;
    arcade.viewport.hidden = false;
    arcade.viewport.classList.remove("is-match");
    arcade.viewport.querySelector("#arcadeValue").hidden = true;
    if (quiet) {
      arcade.viewport.classList.remove("is-near-miss", "is-resetting");
      setText("arcadeStatus", "Call ended");
      arcade.schedule(() => {
        arcade.viewport.classList.add("is-resetting");
        arcade.schedule(() => {
          arcade.viewport.classList.remove("is-resetting");
          arcade.phase = "idle";
          arcade.viewport.hidden = true;
        }, 270);
      }, 150);
      return;
    }
    arcade.viewport.classList.add("is-near-miss");
    arcade.viewport.classList.remove("is-resetting");
    setText("arcadeStatus", "Cycle reset · next prospect");
    arcade.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-spinning", "is-locking", "is-near-miss");
      if (index === 2) windowElement.classList.add("is-near-miss");
      arcade.reels[index].style.transition = "transform 80ms linear";
      arcade.reels[index].style.transform = index === 2
        ? "translateY(50%) rotateX(-216deg)"
        : "rotateX(-72deg)";
    });
    arcade.flashFailure();
    arcade.playResetTone();
    arcade.vibrate(250);
    arcade.schedule(() => {
      arcade.viewport.classList.add("is-resetting");
      arcade.schedule(() => {
        arcade.viewport.classList.remove("is-resetting", "is-near-miss");
        arcade.phase = "idle";
        if (arcade.pendingSpinKey) {
          const nextKey = arcade.pendingSpinKey;
          arcade.pendingSpinKey = null;
          arcade.startSpin(nextKey);
        } else {
          arcade.viewport.hidden = true;
        }
      }, 270);
    }, 150);
  }

export function flashFailure(arcade) {
    const panel = document.querySelector(".dialer-run-panel");
    panel.classList.add("arcade-failure-flash");
    arcade.schedule(() => panel.classList.remove("arcade-failure-flash"), 150);
  }
