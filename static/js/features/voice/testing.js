import { S, state } from "../../store/state.js";
import { byId } from "../../utils/format.js";
import { showToast } from "../../views/dialogs.js";
import { refreshAudioDevices, routeTestAudio, setMicLevel } from "./device.js";

export async function startMicrophoneTest() {
  if (!window.MediaRecorder || !navigator.mediaDevices?.getUserMedia) {
    showToast("Microphone recording is not supported in this browser.", true);
    return;
  }
  byId("startMicTest").disabled = true;
  try {
    const inputId = byId("audioInputSelect").value || "default";
    const audio = inputId === "default" ? true : { deviceId: { exact: inputId } };
    S.micTestStream = await navigator.mediaDevices.getUserMedia({ audio });
    await refreshAudioDevices();
    S.micTestContext = new (window.AudioContext || window.webkitAudioContext)();
    await S.micTestContext.resume();
    const source = S.micTestContext.createMediaStreamSource(S.micTestStream);
    const analyser = S.micTestContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);
    S.micPeakLevel = 0;
    S.micClippingFrames = 0;
    const samples = new Float32Array(analyser.fftSize);
    const measure = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      let peak = 0;
      for (const sample of samples) {
        sum += sample * sample;
        peak = Math.max(peak, Math.abs(sample));
      }
      S.micPeakLevel = Math.max(S.micPeakLevel, peak);
      if (peak >= 0.98) S.micClippingFrames += 1;
      setMicLevel(Math.sqrt(sum / samples.length) * 400);
      S.micTestFrame = requestAnimationFrame(measure);
    };
    measure();
    S.micTestChunks = [];
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
    S.micTestRecorder = new MediaRecorder(S.micTestStream, mimeType ? { mimeType } : undefined);
    S.micTestRecorder.addEventListener("dataavailable", (event) => {
      if (event.data.size) S.micTestChunks.push(event.data);
    });
    S.micTestRecorder.start();
    byId("audioTestStatus").textContent = "Speak now. The level meter is live and your sample is being recorded locally.";
    byId("stopMicTest").disabled = false;
  } catch (error) {
    cancelAnimationFrame(S.micTestFrame);
    S.micTestStream?.getTracks().forEach((track) => track.stop());
    S.micTestStream = null;
    await S.micTestContext?.close();
    S.micTestContext = null;
    setMicLevel(0);
    byId("startMicTest").disabled = false;
    showToast(error.message || "Could not access the selected microphone.", true);
  }
}

export async function stopMicrophoneTest() {
  const recorder = S.micTestRecorder;
  if (!recorder || recorder.state === "inactive") return;
  byId("stopMicTest").disabled = true;
  await new Promise((resolve) => {
    recorder.addEventListener("stop", resolve, { once: true });
    recorder.stop();
  });
  cancelAnimationFrame(S.micTestFrame);
  S.micTestStream?.getTracks().forEach((track) => track.stop());
  S.micTestStream = null;
  await S.micTestContext?.close();
  S.micTestContext = null;
  S.micTestRecorder = null;
  setMicLevel(0);
  byId("startMicTest").disabled = false;
  const sample = new Blob(S.micTestChunks, { type: recorder.mimeType || "audio/webm" });
  if (!sample.size) {
    byId("audioTestStatus").textContent = "No audio was recorded. Check microphone permission and try again.";
    return;
  }
  if (S.micPlaybackUrl) URL.revokeObjectURL(S.micPlaybackUrl);
  S.micPlaybackUrl = URL.createObjectURL(sample);
  const playback = byId("audioPlayback");
  playback.src = S.micPlaybackUrl;
  playback.hidden = false;
  await routeTestAudio(playback);
  const quality = S.micPeakLevel < 0.025 ? "The mic level is very low" : S.micClippingFrames > 2 ? "The mic is clipping" : "Mic level looks healthy";
  byId("audioTestStatus").textContent = `${quality}. Play the local sample to check clarity and headphone volume.`;
}

export async function testAudioOutput() {
  let context;
  let oscillator;
  const playback = byId("outputTestPlayback");
  try {
    context = new (window.AudioContext || window.webkitAudioContext)();
    await context.resume();
    const destination = context.createMediaStreamDestination();
    playback.srcObject = destination.stream;
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
    byId("audioTestStatus").textContent = "Playing a two-tone output test through the selected device.";
    window.setTimeout(async () => {
      playback.pause();
      playback.srcObject = null;
      await context.close();
      byId("audioTestStatus").textContent = "Output test complete.";
    }, 800);
  } catch (error) {
    oscillator?.stop();
    playback.pause();
    playback.srcObject = null;
    await context?.close();
    showToast(error.message || "Could not play the output test.", true);
  }
}
