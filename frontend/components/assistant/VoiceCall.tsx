"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { askAssistant, routeAssistant, transcribeAudio, VerifyError, type AssistantReply, type Report } from "@/lib/api";
import type { Lang } from "@/lib/i18n";
import { STATE, type State } from "@/lib/tokens";
import { VoiceEngine } from "@/lib/voice";

type Phase = "idle" | "starting" | "listening" | "thinking" | "confirming" | "speaking";
const YES = /^(?:نعم|ايوه|أيوه|ايوا|ايه|إيه|اي|أي|اجل|أجل|بلى|تمام|صح|صحيح|اكيد|أكيد|طيب|حسنا|حسنًا|تحقق|تفضل|يلا|yes|yeah|yep|sure|ok|okay|correct|right|go ahead|verify)/i;
const NO = /^(?:لا|كلا|غلط|خطأ|خطا|مو |ليس|no|nope|wrong|not)/i;

/** The spoken form of a reply: the pointer to the on-screen report is dropped. */
function spoken(text: string): string {
  return text.replace(/التقرير الكامل يعرض النص والمصادر والتفاصيل\.?/, "").replace(/The full report shows the text, the sources and the details\.?/, "").trim();
}

/** A voice conversation with the assistant: listen, read back a heard hadith and ask for confirmation, verify, answer
 *  aloud, listen again. Unclear audio is answered with an apology, never a guess. */
export function VoiceCall(props: {
  lang: Lang;
  report: () => Report | null;
  onUser: (text: string) => void;
  onBot: (r: AssistantReply) => string | undefined;   // returns the stored report id for verifications
  onError: (text: string) => void;
  onStart: () => void;
  onEnd: () => void;
}) {
  const t = useTranslations("assistant");
  const s = useTranslations("states");
  const [phase, setPhase] = useState<Phase>("idle");
  const [heard, setHeard] = useState("");
  const [heardRaw, setHeardRaw] = useState("");
  const [answer, setAnswer] = useState<{ text: string; state?: State; reportId?: string } | null>(null);
  const engine = useRef<VoiceEngine | null>(null);
  const choice = useRef<((yes: boolean) => void) | null>(null);

  useEffect(() => () => engine.current?.stop(), []);   // closing the panel ends the call

  const errorText = (e: unknown) => (e instanceof VerifyError && e.message ? e.message : t("errNetwork"));

  /** Wait for «نعم» / «لا» spoken, or a tap on the buttons, whichever comes first. */
  const confirm = (eng: VoiceEngine, lang: Lang): Promise<boolean> =>
    new Promise((resolve) => {
      let settled = false;
      const settle = (v: boolean) => { if (!settled) { settled = true; choice.current = null; eng.stopListening(); resolve(v); } };
      choice.current = settle;
      (async () => {
        const blob = await eng.listen({ maxSeconds: 6, silenceMs: 900, waitMs: 6000 });
        if (settled) return;
        if (!blob) { settle(false); return; }
        try {
          const a = (await transcribeAudio(blob, lang)).text.replace(/[^\p{L}\s]/gu, "").trim();
          settle(YES.test(a) && !NO.test(a));
        } catch { settle(false); }
      })();
    });

  const run = async () => {
    const eng = new VoiceEngine();
    engine.current = eng;
    props.onStart();
    setPhase("starting"); setHeard(""); setAnswer(null);
    try { await eng.start(); } catch (e) {
      props.onError(e instanceof Error && e.message === "no-recorder" ? t("errNoRecorder") : t("errMic"));
      setPhase("idle"); props.onEnd(); return;
    }
    const lang = props.lang;
    setPhase("speaking");
    await eng.speak(t("vGreeting"), lang);
    let silent = 0;
    while (!eng.aborted) {
      setPhase("listening");
      const blob = await eng.listen({ maxSeconds: 30, silenceMs: 1300, waitMs: 9000 });
      if (eng.aborted) break;
      if (!blob) {
        silent += 1;
        setPhase("speaking");
        if (silent >= 2) { await eng.speak(t("vBye"), lang); break; }
        await eng.speak(t("vNoSpeech"), lang);
        continue;
      }
      silent = 0;
      setPhase("thinking");
      let text = "", heardLang: Lang = lang;
      try {
        const out = await transcribeAudio(blob, lang);
        text = out.text; heardLang = out.lang;
        setHeardRaw(out.corrected && out.heard && out.heard !== out.text ? out.heard : "");
      } catch (e) {
        setPhase("speaking"); await eng.speak(errorText(e), lang); continue;
      }
      setHeard(text);
      props.onUser(text);
      let kind: AssistantReply["kind"] = "out_of_scope";
      try { kind = await routeAssistant(text, heardLang, props.report()); } catch {}
      if (kind === "verify") {
        setPhase("speaking");
        await eng.speak(`${t("vHeard")} ${text}. ${t("vConfirm")}`, heardLang);
        if (eng.aborted) break;
        setPhase("confirming");
        const yes = await confirm(eng, heardLang);
        if (eng.aborted) break;
        if (!yes) { setPhase("speaking"); await eng.speak(t("vRepeat"), lang); continue; }
      }
      setPhase("thinking");
      try {
        const r = await askAssistant(text, heardLang, props.report());
        const reportId = props.onBot(r);
        setAnswer({ text: r.reply, state: r.report?.state, reportId });
        setPhase("speaking");
        await eng.speak(spoken(r.reply), r.lang);
      } catch (e) {
        setPhase("speaking"); await eng.speak(errorText(e), lang);
      }
    }
    eng.stop();
    setPhase("idle");
    props.onEnd();
  };

  const end = () => { engine.current?.stop(); choice.current?.(false); };

  if (phase === "idle") {
    return (
      <button type="button" className="btn btn-primary assistant-talk" onClick={run} data-testid="voice-call-start">
        <span aria-hidden="true">📞</span> {t("talk")}
      </button>
    );
  }
  const color = phase === "listening" ? "#3ee6c0" : phase === "confirming" ? "#f2a93b" : phase === "speaking" ? "#7c6cf0" : "#9d97d6";
  return (
    <div className="voice-call" data-testid="voice-call" data-phase={phase}>
      <div className={`voice-orb${phase === "listening" || phase === "speaking" ? " live" : ""}`} style={{ background: color }} aria-hidden="true">
        {phase === "listening" ? "🎙" : phase === "speaking" ? "🔊" : phase === "confirming" ? "؟" : "…"}
      </div>
      <p role="status" aria-live="polite" data-testid="voice-phase" style={{ margin: 0, fontWeight: 800, fontSize: 16 }}>{t(`phase_${phase}`)}</p>
      {heard && (
        <div className="voice-card">
          <span style={{ fontSize: 12, color: "#5a5d80" }}>{t("vHeardLabel")}</span>
          <p dir="auto" data-testid="voice-heard" style={{ margin: "4px 0 0" }}>{heard}</p>
          {heardRaw && <p dir="auto" style={{ margin: "4px 0 0", fontSize: 12, color: "#5a5d80" }}>{t("asHeard")}: {heardRaw}</p>}
        </div>
      )}
      {phase === "confirming" && (
        <div style={{ display: "flex", gap: 8 }}>
          <button type="button" className="btn btn-s btn-primary" onClick={() => choice.current?.(true)} data-testid="voice-yes">{t("vYes")}</button>
          <button type="button" className="btn btn-s btn-secondary" onClick={() => choice.current?.(false)} data-testid="voice-no">{t("vNo")}</button>
        </div>
      )}
      {answer && (
        <div className="voice-card" data-testid="voice-answer">
          {answer.state && (
            <span style={{ display: "inline-block", marginBottom: 6, padding: "2px 10px", borderRadius: 99, fontSize: 12, fontWeight: 800, background: STATE[answer.state].chipBg, color: STATE[answer.state].chipFg }}>
              {s(`${answer.state}.label`, { grade: "" })}
            </span>
          )}
          <p dir="auto" style={{ margin: 0 }}>{answer.text}</p>
          {answer.reportId && <Link href={`/result/?id=${answer.reportId}`} style={{ display: "inline-block", marginTop: 6, fontWeight: 700 }}>{t("openReport")}</Link>}
        </div>
      )}
      <button type="button" onClick={end} className="btn btn-s" data-testid="voice-call-end" style={{ background: "#c2334c", color: "#fff" }}>{t("endCall")}</button>
      <span style={{ fontSize: 11, color: "#5a5d80", textAlign: "center" }}>{t("voiceNote")}</span>
    </div>
  );
}
