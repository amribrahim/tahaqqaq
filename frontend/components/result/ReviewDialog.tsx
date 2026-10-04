"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { API, createReviewPdf, sendReviewForm, VerifyError, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const EMAIL = /^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/;

/** Human-review request: the person leaves a name and email, the server renders the report it produced as a PDF
 *  (kept for a limited time behind a private link), and the request goes to the review team through the contact form
 *  with that link. Native <dialog>: focus stays inside, Esc closes. */
export function ReviewDialog({ report, open, onClose, onSent }: { report: Report; open: boolean; onClose: () => void; onSent: (pdfUrl: string) => void }) {
  const t = useTranslations("result");
  const s = useTranslations("states");
  const { lang } = useLang();
  const ref = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [trap, setTrap] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (busy) return;
    if (!name.trim() || !EMAIL.test(email.trim())) { setError(t("reviewErrInvalid")); return; }
    setBusy(true); setError("");
    try {
      const pdf = await createReviewPdf(report, lang, name.trim(), email.trim());
      const pdfUrl = `${API}${pdf.path}`;
      const grade = report.grade ? report.grade.grade_ar : "";
      const src = report.source ? `${report.source.book_ar} ${report.source.number}` : "—";
      const message = [
        `طلب مراجعة بشرية من تحقّق`,
        `الاسم: ${name.trim()}`,
        `البريد: ${email.trim()}`,
        `الحالة: ${s(`${pdf.state}.label`, { grade })} (${pdf.confidence}%)`,
        `النص المُدخل: ${report.input_text}`,
        `المصدر: ${src}`,
        ...(report.grade ? [`الحكم: ${report.grade.grade_ar} — ${report.grade.grader_ar}`] : []),
        ``,
        `التقرير PDF (متاح ${pdf.retain_days} يومًا): ${pdfUrl}`,
        `رقم التقرير: ${pdf.report_id}`,
      ].join("\n");
      await sendReviewForm({ name: name.trim(), email: email.trim(), subject: `تحقّق: طلب مراجعة بشرية (${s(`${pdf.state}.label`, { grade })})`, message, botcheck: trap });
      onSent(pdfUrl);
    } catch (err) {
      setError(err instanceof VerifyError && err.code === "rate_limited" ? err.message : err instanceof VerifyError && err.code === "form_failed" ? t("reviewErrSend") : t("reviewErrPdf"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <dialog ref={ref} className="review-dialog" data-testid="review-dialog" aria-labelledby="review-title" onClose={onClose} onCancel={onClose}>
      <form onSubmit={submit} noValidate style={{ display: "flex", flexDirection: "column", gap: 14 }}>
        <h2 id="review-title" className="card-title">{t("reviewTitle")}</h2>
        <p style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: "#3d4066" }}>{t("reviewIntro")}</p>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="label">{t("reviewName")}</span>
          <input data-testid="review-name" className="field" style={{ height: 48, padding: "0 14px", fontSize: 16 }} value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" maxLength={120} required />
        </label>
        <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="label">{t("reviewEmail")}</span>
          <input data-testid="review-email" className="field" type="email" dir="ltr" style={{ height: 48, padding: "0 14px", fontSize: 16 }} value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="email" maxLength={200} required />
        </label>
        {/* spam trap: hidden from people, filled by bots */}
        <input type="checkbox" name="botcheck" tabIndex={-1} aria-hidden="true" checked={trap} onChange={(e) => setTrap(e.target.checked)} style={{ display: "none" }} />
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.7, color: "#5a5d80" }}>{t("reviewConsent", { days: 14 })}</p>
        {error && <p role="alert" data-testid="review-error" style={{ margin: 0, fontSize: 14, color: "#a8324a" }}>{error}</p>}
        <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
          <button type="submit" data-testid="review-submit" className="btn btn-m btn-primary" disabled={busy}>{busy ? t("reviewSending") : t("reviewSend")}</button>
          <button type="button" className="btn btn-m btn-ghost" onClick={onClose} disabled={busy}>{t("reviewCancel")}</button>
        </div>
      </form>
    </dialog>
  );
}
