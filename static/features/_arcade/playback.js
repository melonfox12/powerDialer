import { setDialerText } from "../../_core/format.js";

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
    arcade.forEachViewport((vp) => {
      vp.hidden = false;
      vp.classList.remove("is-match");
      const valueEl = vp.querySelector("[id$='arcadeValue']");
      if (valueEl) valueEl.hidden = true;
    });
    if (quiet) {
      arcade.forEachViewport((vp) => vp.classList.remove("is-near-miss", "is-resetting"));
      setDialerText("arcadeStatus", "Call ended");
      arcade.schedule(() => {
        arcade.forEachViewport((vp) => vp.classList.add("is-resetting"));
        arcade.schedule(() => {
          arcade.forEachViewport((vp) => {
            vp.classList.remove("is-resetting");
            vp.hidden = true;
          });
          arcade.phase = "idle";
        }, 270);
      }, 150);
      return;
    }
    arcade.forEachViewport((vp) => {
      vp.classList.add("is-near-miss");
      vp.classList.remove("is-resetting");
    });
    setDialerText("arcadeStatus", "Cycle reset · next prospect");
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
      arcade.forEachViewport((vp) => vp.classList.add("is-resetting"));
      arcade.schedule(() => {
        arcade.forEachViewport((vp) => {
          vp.classList.remove("is-resetting", "is-near-miss");
          vp.hidden = true;
        });
        arcade.phase = "idle";
        if (arcade.pendingSpinKey) {
          const nextKey = arcade.pendingSpinKey;
          arcade.pendingSpinKey = null;
          arcade.startSpin(nextKey);
        }
      }, 270);
    }, 150);
  }

export function flashFailure(arcade) {
    for (const panel of document.querySelectorAll("#dialerTabPanel, #aiDialerAgentTabPanel")) {
      panel.classList.add("arcade-failure-flash");
      arcade.schedule(() => panel.classList.remove("arcade-failure-flash"), 150);
    }
  }
