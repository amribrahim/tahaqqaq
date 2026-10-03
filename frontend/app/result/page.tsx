"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { requestReview, verifyStream, VerifyError, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { timeOf } from "@/lib/format";
import { addHistory, getPending, getReport, setPending, setReport } from "@/lib/session";
import { StatusBanner } from "@/components/result/StatusBanner";
import { LoadingPanel, SkeletonCards } from "@/components/result/LoadingPanel";
import { DiffCard } from "@/components/result/Diff";
import { TranslationCard, TermsCard } from "@/components/result/TranslationCard";
import { GradeCard } from "@/components/result/GradeCard";
import { AbstainCard } from "@/components/result/AbstainCard";
import { Candidates } from "@/components/result/Candidates";
import { Actions } from "@/components/result/Actions";
import { ErrorCard } from "@/components/result/ErrorCard";
import { ExplanationCard } from "@/components/result/ExplanationCard";
import { SegmentsCard } from "@/components/result/Segments";
import { DorarCard } from "@/components/result/DorarCard";

export default function ResultPage() {
  return <Suspense fallback={null}><ResultView /></Suspense>;
}

function ResultView() {
  const params = useSearchParams();
  const id = params.get("id") || "";
  const t = useTranslations("result");
  const { lang } = useLang();
  const [status, setStatus] = useState<"loading" | "done" | "error" | "missing">("loading");
  const [step, setStep] = useState(0);
  const [report, setRep] = useState<Report | null>(null);
  const [err, setErr] = useState<{ code: string; message: string }>({ code: "", message: "" });
  const [reviewSent, setReviewSent] = useState(false);
  const [inputText, setInputText] = useState("");
  const running = useRef(false);

  const run = useCallback(async () => {
    if (!id) { setStatus("missing"); return; }
    const cached = getReport(id);
    if (cached) { setRep(cached); setStatus("done"); return; }
    let pending = getPending(id);
    // Shareable / direct links: /result/?id=<any>&text=<quote>
    const direct = params.get("text");
    if (!pending && direct) { pending = { text: direct, via: "text" }; setPending(id, pending); }
    if (!pending) { setStatus("missing"); return; }
    if (running.current) return;
    running.current = true;
    setInputText(pending.text || pending.url || "");
    setStatus("loading"); setStep(0);
    try {
      const r = await verifyStream({ text: pending.text, url: pending.url, lang, via: pending.via }, (st) => setStep(Math.max(0, st)));
      r.id = id;  // the session id in the URL is the key for the cached report and the history row
      r.via = pending.via;
      if (pending.extracted) r.extracted_text = pending.extracted;
      setReport(id, r); addHistory(r);
      setRep(r); setStatus("done");
    } catch (e) {
      setErr(e instanceof VerifyError ? { code: e.code, message: e.message } : { code: "sources_unreachable", message: String(e) });
      setStatus("error");
    } finally { running.current = false; }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  useEffect(() => { run(); }, [run]);

  const onExport = () => {
    if (!report) return;
    // The browser's print dialog saves a real PDF: Arabic shaping and RTL come out right and the text stays selectable.
    // The page title becomes the suggested file name.
    const prev = document.title;
    const stamp = (report.created_at || new Date().toISOString()).slice(0, 16).replace("T", "-").replace(":", "");
    document.title = `${t("pdfFileName")}-${stamp}`;
    const restore = () => { document.title = prev; window.removeEventListener("afterprint", restore); };
    window.addEventListener("afterprint", restore);
    window.print();
  };
  const onReview = async () => {
    if (!report || reviewSent) return;
    try { await requestReview(report); } catch {}
    setReviewSent(true);
  };

  const r = report;
  const abstainLike = r?.state === "abstain" || r?.state === "referral";
  const showGrade = r && r.source && !abstainLike;
  const timePill = r ? `${t("today")} · ${timeOf(r.created_at, lang)}` : "";

  return (
    <>
      <section className="hero">
        <div className="wrap" style={{ padding: "28px var(--gutter) 40px", display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "10px 16px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
              <h1 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: "clamp(22px,2.2vw,28px)", color: "#fff" }}>{t("report")}</h1>
              {r && <span style={{ fontSize: 13, color: "#c9c3ff", padding: "4px 12px", border: "1px solid rgba(201,195,255,0.25)", borderRadius: 999 }}>{timePill}</span>}
            </div>
            <span style={{ fontSize: 14, color: "#c9c3ff" }}>{t("note")}</span>
          </div>
          {status === "loading" && <LoadingPanel step={step} />}
          {status === "done" && r && <StatusBanner r={r} />}
        </div>
      </section>

      <main id="main" className="wrap" style={{ padding: "32px var(--gutter) 64px", display: "flex", flexWrap: "wrap", gap: 24, alignItems: "flex-start", width: "100%" }}>
        <div style={{ flex: "999 1 560px", minWidth: 0, display: "flex", flexDirection: "column", gap: 24 }}>
          {status === "loading" && <SkeletonCards inputText={inputText} inputLabel={t("input")} />}
          {status === "error" && <ErrorCard code={err.code} message={err.message} onRetry={run} />}
          {status === "missing" && <section className="card"><p style={{ margin: 0 }}>{t("notFound")}</p></section>}
          {status === "done" && r && (
            <>
              {r.extracted_text && r.via !== "text" && (
                <section className="card" data-testid="extracted-card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <span className="label">{t("extracted")} · {r.via === "image" ? t("viaImage") : t("viaUrl")}</span>
                  <p dir="auto" style={{ margin: 0, fontSize: 17, lineHeight: 1.8, color: "#3d4066" }}>{r.extracted_text}</p>
                </section>
              )}
              {r.machine_translation && (
                <section className="card" data-testid="mt-card" style={{ border: "1.5px dashed #cfc9f5", background: "#fbfaff", boxShadow: "none", display: "flex", flexDirection: "column", gap: 8 }}>
                  <span className="chip" style={{ alignSelf: "flex-start", background: "#ecebfe", color: "#4f3fd0" }}>🤖 {t("mtTitle")} · {r.machine_translation.language}</span>
                  <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("mtBody")}</span>
                  <p dir="ltr" style={{ margin: 0, fontSize: 16, lineHeight: 1.7, textAlign: "left" }}>{r.machine_translation.english}</p>
                </section>
              )}
              {r.segments && r.segments.length > 1 && <SegmentsCard r={r} />}
              {abstainLike && <AbstainCard r={r} onReview={onReview} reviewSent={reviewSent} />}
              {!abstainLike && r.input_lang === "ar" && r.diff_input.length > 0 && <DiffCard r={r} />}
              {!abstainLike && r.translation && <TranslationCard r={r} />}
              {r.glossary_terms.length > 0 && <TermsCard terms={r.glossary_terms} />}
              {showGrade && <GradeCard r={r} />}
              {showGrade && r.source && r.source.kind !== "quran" && <DorarCard r={r} />}
              {r.ai_explanation && <ExplanationCard key={r.id} report={r} text={r.ai_explanation} model={r.ai_model} />}
            </>
          )}
        </div>
        <aside style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 24 }}>
          {status === "done" && r && (
            <>
              {r.state !== "referral" && <Candidates r={r} />}
              <Actions abstain={!!abstainLike} referral={r.state === "referral"} onExport={onExport} onReview={onReview} reviewSent={reviewSent} />
            </>
          )}
        </aside>
        {status === "done" && r && (
          <p className="print-only" data-testid="pdf-footer" style={{ width: "100%", margin: 0, fontSize: 12, color: "#5a5d80", lineHeight: 1.7, borderTop: "1px solid #e4e1f5", paddingTop: 10 }}>
            {t("pdfFooter", { date: new Date(r.created_at).toLocaleString(lang === "ar" ? "ar-SA-u-nu-latn" : "en-GB") })}
          </p>
        )}
      </main>
    </>
  );
}
