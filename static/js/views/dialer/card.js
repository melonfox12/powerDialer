import { S, state } from "../../store/state.js";
import { byId, setText } from "../../utils/format.js";

export function drawProspectWaveform(level = 0, samples = null) {
  const canvas = byId("prospectWaveform");
  const bounds = canvas.getBoundingClientRect();
  if (!bounds.width || !bounds.height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = Math.round(bounds.width * ratio);
  const height = Math.round(bounds.height * ratio);
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, bounds.width, bounds.height);
  const normalized = Math.max(0, Math.min(1, level));
  const count = 44;
  const gap = 3;
  const barWidth = Math.max(2, (bounds.width - gap * (count - 1)) / count);
  const center = bounds.height / 2;
  context.fillStyle = normalized > 0.82 ? "#e1b76d" : "#4cc38a";
  for (let index = 0; index < count; index += 1) {
    let magnitude = normalized;
    if (samples && samples.length) {
      const start = Math.floor(index * samples.length / count);
      const end = Math.max(start + 1, Math.floor((index + 1) * samples.length / count));
      let peak = 0;
      for (let sampleIndex = start; sampleIndex < end && sampleIndex < samples.length; sampleIndex += 1) {
        peak = Math.max(peak, Math.abs(samples[sampleIndex] - 128) / 128);
      }
      magnitude = peak;
    } else if (normalized > 0) {
      const envelope = 0.18 + 0.82 * Math.abs(Math.sin(index * 0.38 + performance.now() / 120));
      magnitude = normalized * envelope;
    }
    const barHeight = Math.max(2, magnitude * bounds.height);
    const x = index * (barWidth + gap);
    context.fillRect(x, center - barHeight / 2, barWidth, barHeight);
  }
  const shown = samples && samples.length
    ? Math.round(Math.max(...Array.from(samples, (sample) => Math.abs(sample - 128) / 128)) * 100)
    : Math.round(normalized * 100);
  setText("prospectAudioLevel", `${Math.max(0, Math.min(100, shown))}%`);
}

export function stopProspectWaveform() {
  cancelAnimationFrame(S.waveformFrame);
  S.waveformFrame = 0;
  try { S.waveformSource?.disconnect(); } catch (error) { console.warn("Waveform source could not disconnect:", error); }
  S.waveformSource = null;
  S.waveformAnalyser = null;
  drawProspectWaveform(0);
}

export function startProspectWaveform(call) {
  stopProspectWaveform();
  const AudioContextType = window.AudioContext || window.webkitAudioContext;
  const bind = () => {
    const stream = typeof call?.getRemoteStream === "function" ? call.getRemoteStream() : null;
    if (!stream?.getAudioTracks?.().length || !AudioContextType) return false;
    if (!S.audioContext) S.audioContext = new AudioContextType();
    if (S.audioContext.state === "suspended") S.audioContext.resume().catch(() => {});
    S.waveformAnalyser = S.audioContext.createAnalyser();
    S.waveformAnalyser.fftSize = 256;
    S.waveformSource = S.audioContext.createMediaStreamSource(stream);
    S.waveformSource.connect(S.waveformAnalyser);
    const data = new Uint8Array(S.waveformAnalyser.fftSize);
    const paint = () => {
      if (!S.waveformAnalyser || S.voiceCall !== call) return;
      S.waveformAnalyser.getByteTimeDomainData(data);
      let energy = 0;
      for (let index = 0; index < data.length; index += 1) {
        const centered = (data[index] - 128) / 128;
        energy += centered * centered;
      }
      drawProspectWaveform(Math.min(1, Math.sqrt(energy / data.length) * 4), data);
      S.waveformFrame = requestAnimationFrame(paint);
    };
    paint();
    return true;
  };
  if (!bind()) {
    let tries = 0;
    const retry = () => {
      if (S.voiceCall !== call || bind() || tries > 24) return;
      tries += 1;
      setTimeout(retry, 250);
    };
    retry();
  }
}

export function renderDialedProspect() {
  const dialingCallLead = (state.in_flight || []).find((call) =>
    ["creating", "ringing", "listening", "live"].includes(call.state)
  )?.lead;
  const dialed = state.active_lead || dialingCallLead || state.pending_outcome || null;
  const dialedName = String(dialed?.name || "").trim();
  const dialedBusiness = String(dialed?.business || "").trim();
  const dialedTitle = dialedName || dialedBusiness;
  const dialedSubtitle = dialedBusiness && dialedBusiness !== dialedTitle ? dialedBusiness : "";
  const dialedPlate = byId("dialedProspect");
  dialedPlate.classList.toggle("is-empty", !dialedTitle);
  setText("dialedProspectName", dialedTitle || "No one is being dialed");
  byId("dialedProspectBusiness").hidden = !dialedSubtitle;
  setText("dialedProspectBusiness", dialedSubtitle);
}
