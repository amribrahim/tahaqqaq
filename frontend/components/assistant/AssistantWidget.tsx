"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useRef, useState } from "react";
import { askAssistant, transcribeAudio, VerifyError, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { addHistory, getReport, newId, setReport } from "@/lib/session";
import { STATE, type State } from "@/lib/tokens";

type Msg = { role: "user" | "bot"; text: string; error?: boolean; reportId?: string; state?: State };
const STORE = "tahqaq.assistant.messages";
const MAX_SECONDS = 60;
const VOICE_RMS = 0.02;          // loudness above which a 250 ms sample counts as sound
const MIN_VOICED_SECONDS = 0.5;  // less audible sound than this: treated as silence, nothing is sent

function pickMime(): string {
  if (typeof MediaRecorder === "undefined") return "";
  for (const m of ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"]) {
    if (MediaRecorder.isTypeSupported(m)) return m;
  }
  return "";
}

/** The report open on the page, if any: sent as context so the assistant can explain it. */
function openReport(): Report | null {
  if (typeof window === "undefined" || !window.location.pathname.startsWith("/result")) return null;
  const id = new URLSearchParams(window.location.search).get("id");
  return id ? getReport(id) : null;
}

/** Floating assistant (bottom right): verify a hadith by text or voice, explain the open report, answer questions about
 *  the tool. Limited scope by design; every ruling it shows is quoted from the verification report. */
export function AssistantWidget() {
  const t = useTranslations("assistant");
  const s = useTranslations("states");
  const { lang } = useLang();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [rec, setRec] = useState<"idle" | "recording" | "transcribing">("idle");
  const [seconds, setSeconds] = useState(0);
  const [pending, setPending] = useState<string | null>(null);
  const [speak, setSpeak] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  const field = useRef<HTMLTextAreaElement>(null);
  const log = useRef<HTMLDivElement>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAt = useRef(0);
  // loudness while recording: a recording with almost no voiced audio is refused locally, before any upload
  const meter = useRef<{ ctx: AudioContext; analyser: AnalyserNode; buf: Float32Array<ArrayBuffer>; voiced: number } | null>(null)

  const save = (next: Msg[]) => { try { sessionStorage.setItem(STORE, JSON.stringify(next.slice(-40))); } catch {} };
  const push = (m: Msg) => setMsgs((cur) => { const next = [...cur, m]; save(next); return next; });
  const scrollDown = () => requestAnimationFrame(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; });

  const say = (text: string, replyLang: string) => {
    if (!speak || typeof speechSynthesis === "undefined") return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = replyLang === "ar" ? "ar-SA" : "en-US";
    const voice = speechSynthesis.getVoices().find((v) => v.lang.toLowerCase().startsWith(replyLang === "ar" ? "ar" : "en"));
    if (voice) u.voice = voice;
    speechSynthesis.speak(u);
  };

  const toggle = () => {
    if (open) { close(); return; }
    if (msgs.length === 0) {
      try { const saved = JSON.parse(sessionStorage.getItem(STORE) || "[]"); if (Array.isArray(saved)) setMsgs(saved); } catch {}
    }
    setOpen(true);
    requestAnimationFrame(() => field.current?.focus());
    scrollDown();
  };

  const close = () => {
    if (rec === "recording") stopRecording(true);
    if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel();
    setOpen(false);
    requestAnimationFrame(() => button.current?.focus());
  };

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setInput(""); setPending(null);
    push({ role: "user", text: message });
    setBusy(true); scrollDown();
    try {
      const r = await askAssistant(message, lang, openReport());
      let reportId: string | undefined;
      if (r.kind === "verify" && r.report) {
        reportId = newId();
        const rep = { ...r.report, id: reportId, via: "text" as const };
        setReport(reportId, rep); addHistory(rep);
      }
      push({ role: "bot", text: r.reply, reportId, state: r.report?.state });
      say(r.reply, r.lang);
    } catch (e) {
      push({ role: "bot", text: e instanceof VerifyError && e.message ? e.message : t("errNetwork"), error: true });
    } finally { setBusy(false); scrollDown(); }
  };

  const startRecording = async () => {
    const mime = pickMime();
    if (!mime || !navigator.mediaDevices?.getUserMedia) { push({ role: "bot", text: t("errNoRecorder"), error: true }); return; }
    let stream: MediaStream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); } catch { push({ role: "bot", text: t("errMic"), error: true }); return; }
    const mr = new MediaRecorder(stream, { mimeType: mime });
    chunks.current = [];
    mr.ondataavailable = (ev) => { if (ev.data.size) chunks.current.push(ev.data); };
    mr.onstop = () => { stream.getTracks().forEach((tr) => tr.stop()); };
    mr.onstart = () => { startedAt.current = performance.now(); };
    try {
      const ctx = new AudioContext();
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 2048;
      ctx.createMediaStreamSource(stream).connect(analyser);
      meter.current = { ctx, analyser, buf: new Float32Array(analyser.fftSize), voiced: 0 };
    } catch { meter.current = null; }
    recorder.current = mr;
    startedAt.current = 0;
    mr.start();
    setSeconds(0); setRec("recording"); setPending(null);
    timer.current = setInterval(() => {
      const sec = startedAt.current ? Math.floor((performance.now() - startedAt.current) / 1000) : 0;
      const m = meter.current;
      if (m) {
        m.analyser.getFloatTimeDomainData(m.buf);
        let sum = 0;
        for (let i = 0; i < m.buf.length; i++) sum += m.buf[i] * m.buf[i];
        if (Math.sqrt(sum / m.buf.length) > VOICE_RMS) m.voiced += 0.25;   // seconds of audible sound (sampled every 250 ms)
      }
      setSeconds(sec);
      if (sec >= MAX_SECONDS) stopRecording(false);
    }, 250);
  };

  const stopRecording = (discard: boolean) => {
    const mr = recorder.current;
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
    if (!mr || mr.state === "inactive") { setRec("idle"); return; }
    const elapsed = startedAt.current ? (performance.now() - startedAt.current) / 1000 : 0;
    const voiced = meter.current ? meter.current.voiced : null;
    meter.current?.ctx.close().catch(() => {});
    meter.current = null;
    mr.onstop = async () => {
      mr.stream.getTracks().forEach((tr) => tr.stop());
      if (discard) { setRec("idle"); return; }
      if (elapsed < 1) { setRec("idle"); push({ role: "bot", text: t("errShort"), error: true }); return; }
      if (voiced !== null && voiced < MIN_VOICED_SECONDS) { setRec("idle"); push({ role: "bot", text: t("errSilent"), error: true }); return; }
      setRec("transcribing"); scrollDown();
      try {
        const out = await transcribeAudio(new Blob(chunks.current, { type: mr.mimeType }), lang);
        setPending(out.text);
      } catch (e) {
        push({ role: "bot", text: e instanceof VerifyError && e.message ? e.message : t("errNetwork"), error: true });
      } finally { setRec("idle"); scrollDown(); }
    };
    mr.stop();
  };

  const recordable = typeof window !== "undefined" && typeof MediaRecorder !== "undefined";

  return (
    <div className="no-print" dir={lang === "ar" ? "rtl" : "ltr"}>
      {open && (
        <section id="assistant-panel" role="dialog" aria-label={t("title")} data-testid="assistant-panel" className="assistant-panel"
          onKeyDown={(e) => { if (e.key === "Escape") close(); }}>
          <header style={{ display: "flex", alignItems: "center", gap: 10, padding: "14px 16px", background: "#0d1035", color: "#fff" }}>
            <span aria-hidden="true" style={{ width: 34, height: 34, borderRadius: 10, background: "#3ee6c0", color: "#0d1035", display: "grid", placeItems: "center", fontWeight: 800 }}>✓</span>
            <div style={{ display: "flex", flexDirection: "column", minWidth: 0, flex: 1 }}>
              <strong className="font-cairo" style={{ fontSize: 16 }}>{t("title")} <span style={{ fontSize: 11, fontWeight: 700, padding: "2px 8px", borderRadius: 99, background: "rgba(124,108,240,0.35)", marginInlineStart: 6 }}>{t("aiLabel")}</span></strong>
              <span style={{ fontSize: 12, color: "#c9c3ff" }}>{t("subtitle")}</span>
            </div>
            <button type="button" onClick={() => { setSpeak((v) => !v); if (typeof speechSynthesis !== "undefined") speechSynthesis.cancel(); }}
              aria-pressed={speak} aria-label={speak ? t("speakOff") : t("speakOn")} title={speak ? t("speakOff") : t("speakOn")} data-testid="assistant-speak"
              style={{ background: speak ? "#3ee6c0" : "transparent", color: speak ? "#0d1035" : "#fff", border: "1px solid rgba(201,195,255,0.4)", borderRadius: 10, width: 36, height: 36, cursor: "pointer" }}>🔊</button>
            <button type="button" onClick={close} aria-label={t("close")} data-testid="assistant-close"
              style={{ background: "transparent", color: "#fff", border: "1px solid rgba(201,195,255,0.4)", borderRadius: 10, width: 36, height: 36, cursor: "pointer", fontSize: 18 }}>×</button>
          </header>

          <div ref={log} role="log" aria-live="polite" tabIndex={0} aria-label={t("title")} data-testid="assistant-log" style={{ flex: 1, overflowY: "auto", padding: 14, display: "flex", flexDirection: "column", gap: 10, background: "#f6f5fb" }}>
            <div className="assistant-bubble bot">{t("welcome")}</div>
            {msgs.map((m, i) => (
              <div key={i} className={`assistant-bubble ${m.role}${m.error ? " error" : ""}`} data-testid={m.role === "user" ? "assistant-user" : "assistant-bot"} role={m.error ? "alert" : undefined}>
                <span className="sr-only">{m.role === "user" ? t("you") : t("bot")}: </span>
                {m.state && (
                  <span data-testid="assistant-state" data-state={m.state} style={{ display: "inline-block", marginBottom: 6, padding: "2px 10px", borderRadius: 99, fontSize: 12, fontWeight: 800, background: STATE[m.state].chipBg, color: STATE[m.state].chipFg }}>
                    {s(`${m.state}.label`, { grade: "" })}
                  </span>
                )}
                <p dir="auto" style={{ margin: 0 }}>{m.text}</p>
                {m.reportId && <Link href={`/result/?id=${m.reportId}`} data-testid="assistant-report-link" style={{ display: "inline-block", marginTop: 8, fontWeight: 700 }}>{t("openReport")}</Link>}
              </div>
            ))}
            {busy && <div className="assistant-bubble bot" aria-busy="true">{t("thinking")}</div>}
            {rec === "transcribing" && <div className="assistant-bubble bot" aria-busy="true">{t("transcribing")}</div>}
            {pending !== null && (
              <div className="assistant-bubble confirm" data-testid="assistant-confirm">
                <strong style={{ fontSize: 13 }}>{t("confirmTitle")}</strong>
                <p dir="auto" style={{ margin: "6px 0 10px" }} data-testid="assistant-transcript">{pending}</p>
                <div style={{ display: "flex", gap: 8 }}>
                  <button type="button" className="btn btn-s btn-primary" onClick={() => send(pending)} data-testid="assistant-confirm-send">{t("confirmSend")}</button>
                  <button type="button" className="btn btn-s btn-secondary" onClick={() => { setInput(pending); setPending(null); field.current?.focus(); }} data-testid="assistant-confirm-edit">{t("confirmEdit")}</button>
                </div>
              </div>
            )}
          </div>

          <form onSubmit={(e) => { e.preventDefault(); send(input); }} style={{ display: "flex", flexDirection: "column", gap: 6, padding: 12, borderTop: "1px solid #e4e1f5", background: "#fff" }}>
            <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
              <label htmlFor="assistant-input" className="sr-only">{t("inputLabel")}</label>
              <textarea id="assistant-input" ref={field} value={input} onChange={(e) => setInput(e.target.value)} rows={2} maxLength={2000} dir="auto"
                placeholder={t("placeholder")} data-testid="assistant-input" disabled={rec !== "idle"}
                onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
                style={{ flex: 1, resize: "none", border: "1.5px solid #d8d4ee", borderRadius: 12, padding: "8px 10px", fontSize: 15, fontFamily: "inherit" }} />
              {recordable && (
                <button type="button" data-testid="assistant-mic" aria-pressed={rec === "recording"} disabled={rec === "transcribing" || busy}
                  aria-label={rec === "recording" ? t("stop") : t("mic")} title={rec === "recording" ? t("stop") : t("mic")}
                  onClick={() => (rec === "recording" ? stopRecording(false) : startRecording())}
                  style={{ width: 44, height: 44, borderRadius: 12, border: 0, cursor: "pointer", background: rec === "recording" ? "#e7647a" : "#ecebfe", color: rec === "recording" ? "#fff" : "#4f3fd0", fontSize: 18 }}>
                  {rec === "recording" ? "■" : "🎤"}
                </button>
              )}
              <button type="submit" className="btn btn-primary" disabled={busy || !input.trim() || rec !== "idle"} data-testid="assistant-send" style={{ height: 44, padding: "0 16px", borderRadius: 12 }}>{t("send")}</button>
            </div>
            <span style={{ fontSize: 11, color: "#5a5d80" }} aria-live="polite">
              {rec === "recording" ? t("recording", { s: seconds }) : t("voiceNote")}
            </span>
            {msgs.length > 0 && (
              <button type="button" onClick={() => { setMsgs([]); save([]); }} style={{ alignSelf: "flex-start", background: "none", border: 0, color: "#4f3fd0", fontSize: 12, cursor: "pointer", padding: 0 }}>{t("clear")}</button>
            )}
          </form>
        </section>
      )}
      <button ref={button} type="button" onClick={toggle} aria-expanded={open} aria-controls="assistant-panel" aria-label={t("open")} data-testid="assistant-open" className="assistant-fab">
        <span aria-hidden="true" style={{ fontSize: 22 }}>{open ? "×" : "💬"}</span>
        <span className="assistant-fab-label">{t("open")}</span>
      </button>
    </div>
  );
}
