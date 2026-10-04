/** Audio engine for the assistant's voice conversation.
 *  - listen(): records from the microphone and stops by itself when the speaker has finished (silence after speech),
 *    or returns null when nobody spoke;
 *  - speak(): reads a reply aloud sentence by sentence with the natural voice from /api/tts (the next sentence is
 *    generated while the current one plays), falling back to the device's own voice when no voice provider answers.
 *  Nothing is recorded while the assistant is speaking (no echo), and every step can be cancelled. */
import { API } from "./api";

const VOICE_RMS = 0.02;      // loudness above which a 100 ms sample counts as speech
const SPEECH_START_MS = 300;  // this much sound starts an utterance

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/** A short silent WAV: played inside the click that starts the call so phones allow later playback. */
function silentWav(): string {
  const n = 800, buf = new ArrayBuffer(44 + n * 2), v = new DataView(buf);
  const w = (o: number, s: string) => { for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); v.setUint32(4, 36 + n * 2, true); w(8, "WAVE"); w(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true);
  v.setUint16(22, 1, true); v.setUint32(24, 8000, true); v.setUint32(28, 16000, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  w(36, "data"); v.setUint32(40, n * 2, true);
  return URL.createObjectURL(new Blob([buf], { type: "audio/wav" }));
}

/** Sentences of a reply, so playback can start before the whole reply is synthesised. */
export function sentences(text: string): string[] {
  return text.split(/(?<=[.!؟?。])\s+/).map((s) => s.trim()).filter(Boolean);
}

export class VoiceEngine {
  private stream: MediaStream | null = null;
  private ctx: AudioContext | null = null;
  private analyser: AnalyserNode | null = null;
  private buf: Float32Array<ArrayBuffer> | null = null;
  private player: HTMLAudioElement | null = null;
  private cancelListen: (() => void) | null = null;
  aborted = false;

  /** Playback only (no microphone), from the user's click: lets the assistant speak when the panel opens. */
  startPlayback(): void {
    if (this.player) return;
    this.player = new Audio();
    this.player.src = silentWav();
    this.player.play().catch(() => {});
  }

  /** Must be called from the user's click: microphone permission, audio unlock. */
  async start(): Promise<void> {
    if (!pickMime() || !navigator.mediaDevices?.getUserMedia) throw new Error("no-recorder");
    this.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    this.ctx = new AudioContext();
    await this.ctx.resume();
    this.analyser = this.ctx.createAnalyser();
    this.analyser.fftSize = 2048;
    this.ctx.createMediaStreamSource(this.stream).connect(this.analyser);
    this.buf = new Float32Array(this.analyser.fftSize);
    this.startPlayback();
  }

  level(): number {
    if (!this.analyser || !this.buf) return 0;
    this.analyser.getFloatTimeDomainData(this.buf);
    let sum = 0;
    for (let i = 0; i < this.buf.length; i++) sum += this.buf[i] * this.buf[i];
    return Math.sqrt(sum / this.buf.length);
  }

  /** Record one utterance. Resolves with the audio when the speaker stops, or null when nobody spoke in `waitMs`. */
  listen(opts: { maxSeconds: number; silenceMs: number; waitMs: number }): Promise<Blob | null> {
    const stream = this.stream;
    if (!stream || this.aborted) return Promise.resolve(null);
    return new Promise((resolve) => {
      const mr = new MediaRecorder(stream, { mimeType: pickMime() });
      const chunks: Blob[] = [];
      let spoke = false, soundMs = 0, quietMs = 0, elapsed = 0, done = false;
      mr.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
      const finish = (keep: boolean) => {
        if (done) return;
        done = true;
        clearInterval(tick);
        this.cancelListen = null;
        mr.onstop = () => resolve(keep && spoke && !this.aborted ? new Blob(chunks, { type: mr.mimeType }) : null);
        if (mr.state !== "inactive") mr.stop(); else resolve(null);
      };
      this.cancelListen = () => finish(false);
      const tick = setInterval(() => {
        elapsed += 100;
        if (this.level() > VOICE_RMS) { soundMs += 100; quietMs = 0; if (soundMs >= SPEECH_START_MS) spoke = true; }
        else if (spoke) quietMs += 100;
        if (this.aborted) finish(false);
        else if (spoke && quietMs >= opts.silenceMs) finish(true);
        else if (!spoke && elapsed >= opts.waitMs) finish(false);
        else if (elapsed >= opts.maxSeconds * 1000) finish(true);
      }, 100);
      mr.start();
    });
  }

  /** Stop the current listen (e.g. the user tapped a button instead of answering aloud). */
  stopListening(): void { this.cancelListen?.(); }

  private async fetchVoice(text: string, lang: string): Promise<string | null> {
    try {
      const r = await fetch(`${API}/api/tts`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, lang }) });
      if (!r.ok) return null;
      return URL.createObjectURL(await r.blob());
    } catch { return null; }
  }

  private play(url: string): Promise<void> {
    const p = this.player;
    if (!p) return Promise.resolve();
    return new Promise((resolve) => {
      const end = () => { p.onended = null; p.onerror = null; URL.revokeObjectURL(url); resolve(); };
      p.onended = end; p.onerror = end;
      p.src = url;
      p.play().catch(end);
    });
  }

  private deviceVoice(text: string, lang: string): Promise<void> {
    if (typeof speechSynthesis === "undefined") return Promise.resolve();
    return new Promise((resolve) => {
      const u = new SpeechSynthesisUtterance(text);
      u.lang = lang === "ar" ? "ar-SA" : "en-US";
      const v = speechSynthesis.getVoices().find((x) => x.lang.toLowerCase().startsWith(lang === "ar" ? "ar" : "en"));
      if (v) u.voice = v;
      u.onend = () => resolve(); u.onerror = () => resolve();
      speechSynthesis.speak(u);
    });
  }

  /** Read a reply aloud: natural voice sentence by sentence (next one prefetched), device voice as the fallback. */
  async speak(text: string, lang: string): Promise<void> {
    const parts = sentences(text);
    let next = parts.length ? this.fetchVoice(parts[0], lang) : null;
    for (let i = 0; i < parts.length && !this.aborted; i++) {
      const url = await next;
      next = i + 1 < parts.length ? this.fetchVoice(parts[i + 1], lang) : null;
      if (this.aborted) { if (url) URL.revokeObjectURL(url); break; }
      if (url) await this.play(url);
      else await this.deviceVoice(parts[i], lang);
    }
  }

  /** Stop speaking without ending the engine (a new reply replaces the one being read). */
  hush(): void {
    if (this.player) this.player.pause();
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
  }

  stop(): void {
    this.aborted = true;
    this.cancelListen?.();
    if (this.player) { this.player.pause(); this.player.src = ""; }
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close().catch(() => {});
  }
}
