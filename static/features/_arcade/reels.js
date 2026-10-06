import { setText } from "../../_core/format.js";

export function stopTicking(arcade) {
    clearInterval(arcade.tickTimer);
    arcade.tickTimer = 0;
  }

export function startSpin(arcade, leadKey) {
    if (!arcade.preferences.enabled) return;
    if (arcade.phase === "resetting") {
      arcade.pendingSpinKey = leadKey;
      return;
    }
    if (arcade.phase === "spinning" && arcade.activeLeadKey === leadKey) return;
    arcade.clearTimers();
    arcade.stopParticles();
    arcade.activeLeadKey = leadKey;
    arcade.phase = "spinning";
    arcade.viewport.hidden = false;
    arcade.viewport.classList.remove("is-resetting", "is-near-miss", "is-match");
    arcade.viewport.querySelector("#arcadeValue").hidden = true;
    arcade.viewport.querySelector("#arcadeValue").textContent = "";
    setText("arcadeStatus", "Evaluating connection");
    arcade.reelWindows.forEach((windowElement, index) => {
      windowElement.classList.remove("is-locking", "is-near-miss");
      windowElement.classList.toggle("is-spinning", arcade.preferences.reels);
      arcade.reels[index].style.transition = "";
      arcade.reels[index].style.transform = "";
    });
    arcade.startTicking();
  }

export function startTicking(arcade) {
    arcade.stopTicking();
    if (!arcade.canPlaySound()) return;
    arcade.tickCount = 0;
    arcade.tickTimer = setInterval(() => {
      arcade.tickCount += 1;
      arcade.playTick(540 + Math.min(900, arcade.tickCount * 12));
    }, 50);
  }

export function match(arcade, lead) {
    if (!arcade.preferences.enabled) return;
    const key = lead?.id || arcade.activeLeadKey || "active-call";
    if (arcade.lastMatchKey === key) return;
    arcade.lastMatchKey = key;
    arcade.activeLeadKey = key;
    arcade.clearTimers();
    arcade.stopTicking();
    arcade.phase = "matched";
    const animationId = ++arcade.valueAnimation;
    arcade.viewport.hidden = false;
    arcade.viewport.classList.remove("is-resetting", "is-near-miss");
    arcade.viewport.classList.add("is-match");
    setText("arcadeStatus", "Connection established");
    for (const [index, windowElement] of arcade.reelWindows.entries()) {
      windowElement.classList.remove("is-spinning", "is-near-miss");
      windowElement.classList.add("is-locking");
      arcade.schedule(() => {
        arcade.reels[index].style.transform = "rotateX(-72deg)";
      }, index * 150);
    }
    const rawValue = lead?.estimated_value ?? lead?.value;
    const value = Number(rawValue);
    const valueElement = arcade.viewport.querySelector("#arcadeValue");
    if (Number.isFinite(value) && value > 0) {
      valueElement.hidden = false;
      arcade.animateValue(value, valueElement, animationId);
    } else {
      valueElement.hidden = true;
      valueElement.textContent = "";
    }
    arcade.burstParticles();
    if (arcade.preferences.shake && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      const panel = document.querySelector(".dialer-run-panel");
      panel.classList.remove("arcade-shake");
      void panel.offsetWidth;
      panel.classList.add("arcade-shake");
      arcade.schedule(() => panel.classList.remove("arcade-shake"), 420);
    }
    arcade.playRewardChime();
    arcade.vibrate([50, 20, 50, 20, 50]);
  }
