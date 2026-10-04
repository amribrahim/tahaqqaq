"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useEffect, useState } from "react";
import { requestReview, verifyStream, VerifyError, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { timeOf } from "@/lib/format";
import { addHistory, getPending, getReport, setPending, setReport, type Pending } from "@/lib/session";
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
import { NarrationsCard } from "@/components/result/NarrationsCard";
import { ReviewDialog } from "@/components/result/ReviewDialog";
import { drawShareCard, shareOrDownload } from "@/lib/shareCard";
import { scriptOf } from "@/lib/lang";

export default function ResultPage() {
  return <Suspense fallback={null}><ResultForId /></Suspense>;
}

/** One ResultView per report id, so moving between reports (e.g. verifying a segment) starts from fresh state. */
function ResultForId() {
  const params = useSearchParams();
  const id = params.get("id") || "";
  return <ResultView key={id} id={id} direct={params.get("text")} />;
}

type Init = { status: "loading" | "done" | "missing"; report: Report | null; pending: Pending | null };

/** What to show first: a cached report, a pending verification, or nothing. This page only renders in the browser
 *  (it reads the query string), so sessionStorage can be read while the state is created. */
function initFor(id: string, direct: string | null): Init {
  if (!id) return { status: "missing", report: null, pending: null };
  const cached = getReport(id);
  if (cached) return { status: "done", report: cached, pending: null };
  let pending = getPending(id);
  // Shareable / direct links: /result/?id=<any>&text=<quote>
  if (!pending && direct) { pending = { text: direct, via: "text" }; setPending(id, pending); }
  return pending ? { status: "loading", report: null, pending } : { status: "missing", report: null, pending: null };
}

function ResultView({ id, direct }: { id: string; direct: string | null }) {
  const t = useTranslations("result");
  const { lang, setLang } = useLang();
  const [init] = useState(() => initFor(id, direct));
  const [status, setStatus] = useState<"loading" | "done" | "error" | "missing">(init.status);
  const [step, setStep] = useState(0);
  const [report, setRep] = useState<Report | null>(init.report);
  const [err, setErr] = useState<{ code: string; message: string }>({ code: "", message: "" });
  const [reviewSent, setReviewSent] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [reviewPdf, setReviewPdf] = useState("");
  const [shareState, setShareState] = useState<"" | "busy" | "shared" | "downloaded">("");
  const s = useTranslations("states");
  const inputText = init.pending?.text || init.pending?.url || "";

  /** Run one verification and report through the callbacks; returns a cancel function. */
  const start = (pending: Pending, inLang: "ar" | "en" = lang) => {
    let alive = true;
    verifyStream({ text: pending.text, url: pending.url, lang: inLang, via: pending.via }, (st) => { if (alive) setStep(Math.max(0, st)); })
      .then((r) => {
        r.server_id = r.id;
        r.id = id;  // the session id in the URL is the key for the cached report and the history row
        r.via = pending.via;
        if (pending.extracted) r.extracted_text = pending.extracted;
        setReport(id, r); addHistory(r);
        if (alive) { setRep(r); setStatus("done"); }
      })
      .catch((e) => {
        if (!alive) return;
        setErr(e instanceof VerifyError ? { code: e.code, message: e.message } : { code: "sources_unreachable", message: String(e) });
        setStatus("error");
      });
    return () => { alive = false; };
  };

  // Start the verification for the pending input this page was opened with.
  useEffect(() => {
    if (!init.pending) return;
    return start(init.pending);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const retry = (inLang: "ar" | "en" = lang) => {
    const pending = getPending(id);
    if (!pending) { setStatus("missing"); return; }
    setStatus("loading"); setStep(0);
    start(pending, inLang);
  };
  // the text is in the other interface language: switch the interface and verify it there (only offered when the
  // text really is in that language; for any other language switching would not help)
  const otherLang = lang === "ar" ? "en" : "ar";
  const canSwitch = !!inputText && !init.pending?.url && scriptOf(inputText) === otherLang;
  const switchLang = () => { setLang(otherLang); retry(otherLang); };

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
  const onShare = async () => {
    if (!report || shareState === "busy") return;
    setShareState("busy");
    try {
      const grade = report.grade ? (lang === "ar" ? report.grade.grade_ar : report.grade.grade_en || report.grade.grade_ar) : "";
      const blob = await drawShareCard(report, lang, {
        brand: t("shareBrand"), tagline: t("shareTagline"), stateLbl: t("stateLbl"), stateLabel: s(`${report.state}.label`, { grade }),
        input: t("input"), ruling: t("grade"), source: t("source"), footer: t("shareFooter"), site: "tahaqqaq.pages.dev",
      });
      setShareState(await shareOrDownload(blob, `${t("pdfFileName")}.png`, t("shareBrand")));
    } catch { setShareState(""); }
  };
  const onReview = () => { if (report && !reviewSent) setReviewOpen(true); };
  const onReviewSent = (pdfUrl: string) => {
    setReviewOpen(false); setReviewPdf(pdfUrl); setReviewSent(true);
    if (report) requestReview(report, `PDF: ${pdfUrl}`).catch(() => {});  // also to the review webhook, when one is configured
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
          {status === "error" && <ErrorCard code={err.code} message={err.message} onRetry={() => retry()} onSwitchLang={canSwitch ? switchLang : undefined} />}
          {status === "missing" && <section className="card"><p style={{ margin: 0 }}>{t("notFound")}</p></section>}
          {status === "done" && r && (
            <>
              {r.extracted_text && r.via !== "text" && (
                <section className="card" data-testid="extracted-card" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                  <span className="label">{t("extracted")} · {r.via === "image" ? t("viaImage") : t("viaUrl")}</span>
                  <p dir="auto" style={{ margin: 0, fontSize: 17, lineHeight: 1.8, color: "#3d4066" }}>{r.extracted_text}</p>
                </section>
              )}
              {r.segments && r.segments.length > 1 && <SegmentsCard r={r} />}
              {abstainLike && <AbstainCard r={r} onReview={onReview} reviewSent={reviewSent} />}
              {!abstainLike && r.input_lang === "ar" && r.diff_input.length > 0 && <DiffCard r={r} />}
              {!abstainLike && r.translation && <TranslationCard r={r} />}
              {r.glossary_terms.length > 0 && <TermsCard terms={r.glossary_terms} />}
              {showGrade && <GradeCard r={r} />}
              {showGrade && r.source && r.source.kind !== "quran" && <DorarCard r={r} />}
              {showGrade && <NarrationsCard r={r} />}
              {r.ai_explanation && <ExplanationCard key={r.id} report={r} text={r.ai_explanation} model={r.ai_model} />}
            </>
          )}
        </div>
        <aside style={{ flex: "1 1 320px", minWidth: 0, display: "flex", flexDirection: "column", gap: 24 }}>
          {status === "done" && r && (
            <>
              {r.state !== "referral" && <Candidates r={r} />}
              <Actions abstain={!!abstainLike} referral={r.state === "referral"} onExport={onExport} onShare={onShare} shareState={shareState} onReview={onReview} reviewSent={reviewSent} reviewPdf={reviewPdf} />
              <ReviewDialog report={r} open={reviewOpen} onClose={() => setReviewOpen(false)} onSent={onReviewSent} />
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
