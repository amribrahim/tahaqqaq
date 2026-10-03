"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function Actions({ abstain, referral = false, copied, onCopy, onReview, reviewSent }: { abstain: boolean; referral?: boolean; copied: boolean; onCopy: () => void; onReview: () => void; reviewSent: boolean }) {
  const t = useTranslations("result");
  const copyBtn = <button key="copy" data-testid="copy-btn" onClick={onCopy} className={`btn btn-l ${abstain ? "btn-secondary" : "btn-primary"}`} style={{ width: "100%" }}>{copied ? t("copied") : t("copy")}</button>;
  const reviewBtn = <button key="review" data-testid="review-btn-aside" onClick={onReview} disabled={reviewSent} className={`btn btn-l ${abstain ? "btn-primary" : "btn-secondary"}`} style={{ width: "100%" }}>{t("review")}</button>;
  return (
    <section className="card" style={{ padding: "clamp(18px,2.2vw,24px)", display: "flex", flexDirection: "column", gap: 12 }}>
      <h3 className="card-title" style={{ marginBottom: 4 }}>{t("actions")}</h3>
      {referral ? [copyBtn] : abstain ? [reviewBtn, copyBtn] : [copyBtn, reviewBtn]}
      {reviewSent && (
        <div data-testid="review-sent" style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 14px", borderRadius: 12, background: "#dcfaf1", color: "#087a62", fontSize: 14, fontWeight: 500, lineHeight: 1.5 }}>
          <span style={{ fontWeight: 800 }}>✓</span>{t("reviewSent")}
        </div>
      )}
      <Link href="/" className="btn btn-ghost" style={{ height: 48, borderRadius: 14, fontSize: 16, width: "100%" }}>{t("another")}</Link>
    </section>
  );
}
