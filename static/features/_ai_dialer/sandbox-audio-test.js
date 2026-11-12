import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { showToast } from "../../_core/notify.js";
import { routeTestAudio } from "../_dialer/_voice/devices.js";
import { isSandboxActive } from "./sandbox.js";

function setMeter(percent) {
  const meter = byId("aiDialerAgent-sandboxMicMeter");
  if (meter) meter.textContent = `Input level ${Math.round(percent)}%`;
}

function setStatus(text) {
  const node = byId("aiDialerAgent-sandboxAudioTestStatus");
  if (node) node.textContent = text || "";
}

function guardsRunningSandbox() {
  if (isSandboxActive()) {
    showToast("Stop the sandbox before running an audio test.", true);
    return true;
  }
  return false;
}

export async function startSandboxMicTest() {
  if (guardsRunningSandbox()) return;
  if (!navigator.mediaDevices?.getUserMedia) {
    showToast("Microphone access is not available in this browser.", true);
    return;
  }
  try {
    S.sandboxMicTestStream = await navigator.mediaDevices.getUserMedia({ audio: true });
    S.sandboxMicTestContext = new (window.AudioContext || window.webkitAudioContext)();
    await S.sandboxMicTestContext.resume();
    const source = S.sandboxMicTestContext.createMediaStreamSource(S.sandboxMicTestStream);
    const analyser = S.sandboxMicTestContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const measure = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const sample of samples) sum += sample * sample;
      setMeter(Math.min(100, Math.sqrt(sum / samples.length) * 400));
      S.sandboxMicTestFrame = requestAnimationFrame(measure);
    };
    measure();
    S.sandboxMicTestChunks = [];
    const mimeType = window.MediaRecorder?.isTypeSupported?.("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : "";
    S.sandboxMicTestRecorder = new MediaRecorder(S.sandboxMicTestStream, mimeType ? { mimeType } : undefined);
    S.sandboxMicTestRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) S.sandboxMicTestChunks.push(event.data);
    });
    S.sandboxMicTestRecorder.start();
    setStatus("Speak now — watching mic level and recording a short sample.");
  } catch (error) {
    await stopSandboxMicTest();
    showToast(error.message || "Could not access the microphone.", true);
  }
}

export async function stopSandboxMicTest() {
  byId("aiDialerAgent-sandboxTestMic")?.removeAttribute("disabled");
  cancelAnimationFrame(S.sandboxMicTestFrame || 0);
  S.sandboxMicTestFrame = 0;
  S.sandboxMicTestStream?.getTracks().forEach((track) => track.stop());
  S.sandboxMicTestStream = null;
  await S.sandboxMicTestContext?.close();
  S.sandboxMicTestContext = null;
  const recorder = S.sandboxMicTestRecorder;
  S.sandboxMicTestRecorder = null;
  if (recorder && recorder.state === "recording") {
    await new Promise((resolve) => {
      recorder.addEventListener("stop", resolve, { once: true });
      recorder.stop();
    });
    const sample = new Blob(S.sandboxMicTestChunks || [], { type: recorder.mimeType || "audio/webm" });
    if (sample.size) {
      if (S.sandboxMicPlaybackUrl) URL.revokeObjectURL(S.sandboxMicPlaybackUrl);
      S.sandboxMicPlaybackUrl = URL.createObjectURL(sample);
      const playback = byId("aiDialerAgent-sandboxTestPlayback");
      if (playback) {
        playback.src = S.sandboxMicPlaybackUrl;
        playback.hidden = false;
        await routeTestAudio(playback);
      }
      setStatus("Sample captured — play it back to check clarity, or run Test headphones.");
    } else {
      setStatus("No audio captured. Check permissions and try again.");
    }
  }
  setMeter(0);
}

export async function testSandboxHeadphones() {
  if (guardsRunningSandbox()) return;
  const playback = byId("aiDialerAgent-sandboxTestPlayback");
  if (!playback) return;
  let context;
  let oscillator;
  try {
    context = new (window.AudioContext || window.webkitAudioContext)();
    await context.resume();
    const destination = context.createMediaStreamDestination();
    playback.srcObject = destination.stream;
    playback.hidden = false;
    await routeTestAudio(playback);
    await playback.play();
    oscillator = context.createOscillator();
    const gain = context.createGain();
    const now = context.currentTime;
    gain.gain.setValueAtTime(0.0001, now);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.04);
    gain.gain.setValueAtTime(0.18, now + 0.25);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.32);
    gain.gain.setValueAtTime(0.0001, now + 0.36);
    gain.gain.linearRampToValueAtTime(0.18, now + 0.4);
    gain.gain.setValueAtTime(0.18, now + 0.6);
    gain.gain.linearRampToValueAtTime(0.0001, now + 0.68);
    oscillator.frequency.setValueAtTime(440, now);
    oscillator.frequency.setValueAtTime(660, now + 0.36);
    oscillator.connect(gain).connect(destination);
    oscillator.start(now);
    oscillator.stop(now + 0.72);
    setStatus("Playing a two-tone test through your selected output device.");
    window.setTimeout(async () => {
      playback.pause();
      playback.srcObject = null;
      await context.close();
      setStatus("Headphone test complete.");
    }, 900);
  } catch (error) {
    oscillator?.stop();
    playback.pause();
    playback.srcObject = null;
    await context?.close();
    showToast(error.message || "Could not play the headphone test.", true);
  }
}

let micTestTimer = 0;

export function bindSandboxAudioTest() {
  byId("aiDialerAgent-sandboxTestMic")?.addEventListener("click", () => {
    window.clearTimeout(micTestTimer);
    const micButton = byId("aiDialerAgent-sandboxTestMic");
    if (micButton) micButton.disabled = true;
    startSandboxMicTest().catch(() => {});
    micTestTimer = window.setTimeout(() => {
      stopSandboxMicTest().catch(() => {});
    }, 4000);
  });
  byId("aiDialerAgent-sandboxTestHeadphones")?.addEventListener("click", () => {
    testSandboxHeadphones().catch(() => {});
  });
}
