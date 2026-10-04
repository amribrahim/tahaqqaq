"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function Actions({ abstain, referral = false, onExport, onShare, shareState, onReview, reviewSent, reviewPdf = "" }: { abstain: boolean; referral?: boolean; onExport: () => void; onShare: () => void; shareState: "" | "busy" | "shared" | "downloaded"; onReview: () => void; reviewSent: boolean; reviewPdf?: string }) {
  const t = useTranslations("result");
  const pdfBtn = <button key="pdf" data-testid="pdf-btn" onClick={onExport} className={`btn btn-l ${abstain ? "btn-secondary" : "btn-primary"}`} style={{ width: "100%" }}>{t("exportPdf")}</button>;
  const shareBtn = <button key="share" data-testid="share-btn" onClick={onShare} disabled={shareState === "busy"} className="btn btn-l btn-secondary" style={{ width: "100%" }}>{shareState === "downloaded" ? t("shareSaved") : shareState === "shared" ? t("shareDone") : t("share")}</button>;
  const reviewBtn = <button key="review" data-testid="review-btn-aside" onClick={onReview} disabled={reviewSent} className={`btn btn-l ${abstain ? "btn-primary" : "btn-secondary"}`} style={{ width: "100%" }}>{t("review")}</button>;
  return (
    <section className="card no-print" style={{ padding: "clamp(18px,2.2vw,24px)", display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 className="card-title" style={{ marginBottom: 4 }}>{t("actions")}</h3>
      {referral ? [pdfBtn] : abstain ? [reviewBtn, pdfBtn, shareBtn] : [pdfBtn, shareBtn, reviewBtn]}
      {reviewSent && (
        <div data-testid="review-sent" style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 14px", borderRadius: 12, background: "#dcfaf1", color: "#087a62", fontSize: 14, fontWeight: 500, lineHeight: 1.5 }}>
          <span style={{ fontWeight: 800 }}>✓</span>
          <span>{t("reviewSent")}{reviewPdf && <> <a data-testid="review-pdf-link" href={reviewPdf} target="_blank" rel="noopener noreferrer" style={{ color: "inherit", fontWeight: 700 }}>{t("reviewOpenPdf")}</a></>}</span>
        </div>
      )}
      <Link href="/" className="btn btn-ghost" style={{ height: 48, borderRadius: 14, fontSize: 16, width: "100%" }}>{t("another")}</Link>
    </section>
  );
}
