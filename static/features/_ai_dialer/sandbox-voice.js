import { S } from "../../_core/state.js";
import { byId } from "../../_core/format.js";
import { postJson, request } from "../../_core/api.js";
import { render } from "../../core.js";
import { showToast } from "../../_core/notify.js";
import { errorText } from "../../_core/notify.js";
import { drawSandboxWaveform } from "../_dialer/card.js";
import { routeTestAudio } from "../_dialer/_voice/devices.js";

const TARGET_RATE = 8000;
const MULAW_BIAS = 0x84;
const MULAW_CLIP = 32635;
const SEND_BATCH_MS = 80;

function speechRecognitionCtor() {
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function voiceState() {
  if (!S.sandboxVoice) {
    S.sandboxVoice = {
      agentId: "",
      pollTimer: 0,
      sendTimer: 0,
      micStream: null,
      audioContext: null,
      processor: null,
      micSource: null,
      analyser: null,
      recognition: null,
      useMulawFallback: false,
      waveformFrame: 0,
      pendingMulaw: [],
      playQueue: [],
      playing: false,
      agentSpeaking: false,
      lastTranscriptSeq: 0,
      capturePaused: false,
      audioSendWarned: false,
      recognitionWanted: false,
      playbackEl: null,
      playbackNode: null,
      agentGain: null,
      pollActive: false,
    };
  }
  return S.sandboxVoice;
}

function sandboxBox(agentId) {
  if (!S.aiSandboxByAgent) S.aiSandboxByAgent = {};
  return S.aiSandboxByAgent[agentId];
}

function mergeSyncPayload(agentId, payload) {
  const box = sandboxBox(agentId);
  if (!box) return;
  box.transcript = payload.transcript || [];
  box.ended = Boolean(payload.ended);
  box.reply_busy = Boolean(payload.reply_busy);
  box.booting = Boolean(payload.booting);
  if (!box.partialProspect) box.partialProspect = "";
}

function linearToMulaw(sample) {
  let sign = (sample >> 8) & 0x80;
  if (sign) sample = -sample;
  if (sample > MULAW_CLIP) sample = MULAW_CLIP;
  sample += MULAW_BIAS;
  let exponent = 7;
  for (let mask = 0x4000; (sample & mask) === 0 && exponent > 0; exponent -= 1, mask >>= 1) {}
  const mantissa = (sample >> (exponent + 3)) & 0x0f;
  return (~(sign | (exponent << 4) | mantissa)) & 0xff;
}

function mulawToLinear(byte) {
  byte = (~byte) & 0xff;
  const sign = byte & 0x80;
  const exponent = (byte >> 4) & 0x07;
  const mantissa = byte & 0x0f;
  let sample = ((mantissa << 3) + MULAW_BIAS) << exponent;
  sample -= MULAW_BIAS;
  if (sign) sample = -sample;
  return Math.max(-32768, Math.min(32767, sample));
}

function downsampleToMulaw(float32, inputRate) {
  if (!float32?.length) return new Uint8Array(0);
  const ratio = inputRate / TARGET_RATE;
  const length = Math.floor(float32.length / ratio);
  const out = new Uint8Array(length);
  for (let index = 0; index < length; index += 1) {
    const sample = float32[Math.floor(index * ratio)] || 0;
    const int16 = Math.max(-32768, Math.min(32767, Math.round(sample * 32768)));
    out[index] = linearToMulaw(int16);
  }
  return out;
}

function bytesToBase64(bytes) {
  let binary = "";
  const chunk = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunk) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunk));
  }
  return btoa(binary);
}

function stopWaveformPaint() {
  const voice = voiceState();
  cancelAnimationFrame(voice.waveformFrame);
  voice.waveformFrame = 0;
  drawSandboxWaveform(0);
}

function startWaveformPaint() {
  const voice = voiceState();
  stopWaveformPaint();
  if (!voice.analyser) return;
  const data = new Uint8Array(voice.analyser.fftSize);
  const paint = () => {
    if (!voice.analyser || voice.agentId !== S.aiDialerSelectedAgentId) return;
    voice.analyser.getByteTimeDomainData(data);
    let energy = 0;
    for (let index = 0; index < data.length; index += 1) {
      const centered = (data[index] - 128) / 128;
      energy += centered * centered;
    }
    drawSandboxWaveform(Math.min(1, Math.sqrt(energy / data.length) * 4), data);
    voice.waveformFrame = requestAnimationFrame(paint);
  };
  paint();
}

async function ensureAgentPlaybackRoute() {
  const voice = voiceState();
  if (!voice.audioContext || voice.playbackNode) return;
  voice.playbackNode = voice.audioContext.createMediaStreamDestination();
  voice.agentGain = voice.audioContext.createGain();
  voice.agentGain.gain.value = Number(byId("testVolumeInput")?.value || 100) / 100;
  voice.agentGain.connect(voice.playbackNode);
  voice.playbackEl = byId("aiDialerAgent-sandboxAgentPlayback");
  if (voice.playbackEl) {
    voice.playbackEl.srcObject = voice.playbackNode.stream;
    await routeTestAudio(voice.playbackEl);
    try {
      await voice.playbackEl.play();
    } catch {
      /* gesture already happened on Start */
    }
  }
}

async function ensureAudioContext() {
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  if (!AudioContextType) throw new Error("This browser cannot play sandbox audio.");
  const voice = voiceState();
  if (!voice.audioContext) {
    voice.audioContext = new AudioContextType();
  }
  await voice.audioContext.resume();
  await ensureAgentPlaybackRoute();
  return voice.audioContext;
}

function mergeMulawChunksBase64(chunks) {
  if (!chunks?.length) return "";
  if (chunks.length === 1) return chunks[0];
  const parts = chunks.map((chunk) => Uint8Array.from(atob(chunk), (char) => char.charCodeAt(0)));
  const total = parts.reduce((sum, part) => sum + part.length, 0);
  const merged = new Uint8Array(total);
  let offset = 0;
  for (const part of parts) {
    merged.set(part, offset);
    offset += part.length;
  }
  return bytesToBase64(merged);
}

async function playMulawBase64(payload) {
  const context = await ensureAudioContext();
  const voice = voiceState();
  const raw = Uint8Array.from(atob(payload), (char) => char.charCodeAt(0));
  const pcm = new Float32Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) {
    pcm[index] = mulawToLinear(raw[index]) / 32768;
  }
  const buffer = context.createBuffer(1, pcm.length, TARGET_RATE);
  buffer.copyToChannel(pcm, 0);
  const source = context.createBufferSource();
  source.buffer = buffer;
  const sink = voice.agentGain || context.destination;
  source.connect(sink);
  await new Promise((resolve) => {
    source.onended = () => resolve();
    source.start();
  });
}

function pauseRecognition() {
  const voice = voiceState();
  voice.recognitionWanted = false;
  try {
    voice.recognition?.stop();
  } catch {
    /* already stopped */
  }
}

function resumeRecognition(agentId) {
  const voice = voiceState();
  if (!voice.recognition || voice.useMulawFallback || voice.capturePaused) return;
  if (voice.agentId !== agentId) return;
  const box = sandboxBox(agentId);
  if (box?.ended || box?.reply_busy) return;
  voice.recognitionWanted = true;
  try {
    voice.recognition.start();
  } catch {
    /* already running */
  }
}

async function sendProspectFinal(agentId, text) {
  const box = sandboxBox(agentId);
  if (!box || box.ended || box.reply_busy) return;
  pauseRecognition();
  box.partialProspect = "";
  box.reply_busy = true;
  render();
  try {
    const payload = await postJson("/api/ai-agents/sandbox/turn", { agent_id: agentId, text });
    mergeSyncPayload(agentId, payload);
    voiceState().lastTranscriptSeq = payload.transcript_seq || voiceState().lastTranscriptSeq;
    if (payload.ended) showToast("Agent ended the call ([END_CALL]).");
    render();
  } catch (error) {
    showToast(errorText(error, "Agent could not reply."), true);
    box.reply_busy = false;
    render();
  } finally {
    if (!box.ended && !box.reply_busy) resumeRecognition(agentId);
    else if (!box.ended) {
      window.setTimeout(() => {
        const latest = sandboxBox(agentId);
        if (latest && !latest.reply_busy && !latest.ended) resumeRecognition(agentId);
      }, 300);
    }
  }
}

function bindSpeechRecognition(agentId) {
  const ctor = speechRecognitionCtor();
  const voice = voiceState();
  if (!ctor) {
    voice.useMulawFallback = true;
    return;
  }
  voice.useMulawFallback = false;
  const recognition = new ctor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = "en-US";
  recognition.onresult = (event) => {
    const box = sandboxBox(agentId);
    if (!box || box.ended || voice.capturePaused || box.reply_busy) return;
    let interim = "";
    let finals = [];
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const piece = event.results[index][0]?.transcript || "";
      if (event.results[index].isFinal) finals.push(piece);
      else interim += piece;
    }
    if (interim.trim()) {
      box.partialProspect = interim.trim();
      render();
    }
    for (const line of finals) {
      const text = line.trim();
      if (text) sendProspectFinal(agentId, text).catch(() => {});
    }
  };
  recognition.onerror = (event) => {
    if (event.error === "not-allowed") {
      showToast("Allow microphone access for live transcript.", true);
      voice.useMulawFallback = true;
    } else if (event.error !== "aborted" && event.error !== "no-speech") {
      voice.useMulawFallback = true;
    }
  };
  recognition.onend = () => {
    if (voice.recognitionWanted && voice.agentId === agentId) {
      try {
        recognition.start();
      } catch {
        /* ignore */
      }
    }
  };
  voice.recognition = recognition;
  voice.recognitionWanted = true;
  try {
    recognition.start();
  } catch {
    voice.useMulawFallback = true;
  }
}

async function drainPlayQueue() {
  const voice = voiceState();
  if (voice.playing) return;
  voice.playing = true;
  voice.agentSpeaking = true;
  voice.capturePaused = true;
  pauseRecognition();
  paintSandboxVoiceChrome();
  try {
    while (voice.playQueue.length) {
      const chunk = voice.playQueue.shift();
      await playMulawBase64(chunk);
    }
  } finally {
    voice.playing = false;
    voice.agentSpeaking = false;
    voice.capturePaused = false;
    paintSandboxVoiceChrome();
    resumeRecognition(voice.agentId);
  }
}

function enqueuePlayback(chunks) {
  if (!chunks?.length) return;
  voiceState().playQueue.push(mergeMulawChunksBase64(chunks));
  drainPlayQueue().catch(() => {});
}

async function pollSandboxSync(agentId) {
  const voice = voiceState();
  if (voice.agentId !== agentId) return;
  try {
    const payload = await request(`/api/ai-agents/sandbox/sync?agent_id=${encodeURIComponent(agentId)}`);
    const box = sandboxBox(agentId);
    const seq = payload.transcript_seq || 0;
    const transcript = payload.transcript || [];
    const changed = box && (seq !== voice.lastTranscriptSeq || box.transcript?.length !== transcript.length);
    if (box) mergeSyncPayload(agentId, payload);
    if (changed) {
      voice.lastTranscriptSeq = seq;
      render();
    }
    if (payload.chunks?.length) enqueuePlayback(payload.chunks);
    if (payload.ended) {
      if (box) box.active = false;
      stopSandboxVoiceKeepServer();
    }
    if (box && !box.reply_busy && !box.ended && !voice.capturePaused) {
      resumeRecognition(agentId);
    }
  } catch {
    /* retry on next tick */
  }
}

async function flushMicBatch(agentId) {
  const voice = voiceState();
  if (!voice.useMulawFallback || voice.agentId !== agentId || voice.capturePaused || !voice.pendingMulaw.length) {
    return;
  }
  const batch = voice.pendingMulaw.splice(0, voice.pendingMulaw.length);
  const encoded = bytesToBase64(batch);
  try {
    const payload = await postJson("/api/ai-agents/sandbox/audio", { agent_id: agentId, payload: encoded });
    mergeSyncPayload(agentId, payload);
    if (payload.transcript_seq !== voice.lastTranscriptSeq) {
      voice.lastTranscriptSeq = payload.transcript_seq || 0;
      render();
    }
  } catch (error) {
    if (!voice.audioSendWarned) {
      voice.audioSendWarned = true;
      showToast(errorText(error, "Sandbox mic audio could not reach the server."), true);
    }
  }
}

function stopSandboxVoiceKeepServer() {
  const voice = voiceState();
  pauseRecognition();
  voice.recognition = null;
  voice.pollActive = false;
  if (voice.pollTimer) window.clearTimeout(voice.pollTimer);
  if (voice.sendTimer) window.clearInterval(voice.sendTimer);
  voice.pollTimer = 0;
  voice.sendTimer = 0;
  voice.processor?.disconnect();
  voice.micSource?.disconnect();
  voice.analyser?.disconnect();
  voice.micStream?.getTracks().forEach((track) => track.stop());
  voice.processor = null;
  voice.micSource = null;
  voice.analyser = null;
  voice.micStream = null;
  voice.pendingMulaw = [];
  voice.playQueue = [];
  voice.agentId = "";
  voice.playing = false;
  voice.agentSpeaking = false;
  voice.capturePaused = false;
  voice.playbackEl?.pause();
  if (voice.playbackEl) voice.playbackEl.srcObject = null;
  voice.playbackNode = null;
  voice.agentGain = null;
  voice.playbackEl = null;
  const box = sandboxBox(S.aiDialerSelectedAgentId);
  if (box) box.partialProspect = "";
  stopWaveformPaint();
  paintSandboxVoiceChrome();
}

export function paintSandboxVoiceChrome() {
  const status = byId("aiDialerAgent-sandboxVoiceStatus");
  const voice = voiceState();
  const box = sandboxBox(voice.agentId || S.aiDialerSelectedAgentId);
  const ended = box?.ended;
  const active = Boolean(voice.agentId);
  if (status) {
    if (!active && !box?.active) {
      status.textContent = "Press Start — agent opens immediately; your words appear as you speak.";
    } else if (ended) {
      status.textContent = "Call ended — press Start to rehearse again or Stop to exit.";
    } else if (voice.agentSpeaking) {
      status.textContent = "Agent speaking…";
    } else if (box?.booting) {
      status.textContent = "Agent connecting…";
    } else if (box?.reply_busy) {
      status.textContent = "Agent thinking…";
    } else if (voice.useMulawFallback) {
      status.textContent = "Mic live — speak, then pause briefly (browser speech assist off).";
    } else {
      status.textContent = "Mic live — your lines appear as you talk.";
    }
  }
}

export async function startSandboxVoice(agentId) {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone access is not available in this browser.");
  }
  await ensureAudioContext();
  const voice = voiceState();
  stopSandboxVoice();
  voice.agentId = agentId;
  const box = sandboxBox(agentId);
  voice.lastTranscriptSeq = box?.transcript_seq || 0;
  voice.micStream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const context = voice.audioContext;
  voice.micSource = context.createMediaStreamSource(voice.micStream);
  voice.analyser = context.createAnalyser();
  voice.analyser.fftSize = 256;
  voice.micSource.connect(voice.analyser);
  const bufferSize = 2048;
  voice.processor = context.createScriptProcessor(bufferSize, 1, 1);
  voice.processor.onaudioprocess = (event) => {
    if (!voice.useMulawFallback || voice.capturePaused || voice.agentId !== agentId) return;
    const input = event.inputBuffer.getChannelData(0);
    const mulaw = downsampleToMulaw(input, context.sampleRate);
    if (mulaw.length) voice.pendingMulaw.push(...mulaw);
  };
  const sink = context.createGain();
  sink.gain.value = 0;
  voice.micSource.connect(voice.processor);
  voice.processor.connect(sink);
  sink.connect(context.destination);
  voice.audioSendWarned = false;
  bindSpeechRecognition(agentId);
  voice.sendTimer = window.setInterval(() => {
    flushMicBatch(agentId).catch(() => {});
  }, SEND_BATCH_MS);
  voice.pollActive = true;
  const pollMs = () => (sandboxBox(agentId)?.booting ? 60 : 120);
  const schedulePoll = () => {
    if (!voice.pollActive || voice.agentId !== agentId) return;
    pollSandboxSync(agentId)
      .catch(() => {})
      .finally(() => {
        if (voice.pollActive && voice.agentId === agentId) {
          voice.pollTimer = window.setTimeout(schedulePoll, pollMs());
        }
      });
  };
  schedulePoll();
  startWaveformPaint();
  paintSandboxVoiceChrome();
  await pollSandboxSync(agentId);
}

export function stopSandboxVoice() {
  stopSandboxVoiceKeepServer();
}
