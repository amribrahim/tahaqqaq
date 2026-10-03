"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";

export function AbstainCard({ r, onReview, reviewSent }: { r: Report; onReview: () => void; reviewSent: boolean }) {
  const t = useTranslations("result");
  const referral = r.state === "referral";
  const list = t.raw(referral ? "refList" : "absList") as string[];
  return (
    <section className="card" data-testid="abstain-card" style={{ padding: "clamp(20px,2.6vw,36px)", display: "flex", flexDirection: "column", gap: 22 }}>
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        <span className="font-cairo" style={{ flex: "none", width: 48, height: 48, borderRadius: "50%", background: referral ? "#ddf2f8" : "#f1eff4", border: `2px solid ${referral ? "#5fd0ec" : "#e7647a"}`, color: referral ? "#0f6a85" : "#a8324a", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 22 }}>
          {referral ? "↗" : "—"}
        </span>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <h3 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(20px,2.2vw,24px)" }}>{t(referral ? "refTitle" : "absTitle")}</h3>
          <p style={{ margin: 0, fontSize: 16, lineHeight: 1.8, color: "#3d4066", textWrap: "pretty" }}>{t(referral ? "refBody" : "absBody")}</p>
        </div>
      </div>
      <div style={{ padding: 20, borderRadius: 14, background: "#f7f6fb", border: "1.5px dashed #d8d5e8", display: "flex", flexDirection: "column", gap: 8 }}>
        <span className="label">{t("input")}</span>
        <p dir="auto" style={{ margin: 0, fontSize: 21, lineHeight: 2, fontWeight: 500, color: "#3d4066" }}>{r.input_text}</p>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <h4 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>{t("absTodo")}</h4>
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 8 }}>
          {list.map((a) => (
            <li key={a} style={{ display: "flex", gap: 10, alignItems: "baseline", fontSize: 15, lineHeight: 1.7 }}>
              <span style={{ flex: "none", width: 6, height: 6, borderRadius: "50%", background: "#7c6cf0", transform: "translateY(-2px)" }} />{a}
            </li>
          ))}
        </ul>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        {!referral && <button data-testid="review-btn" onClick={onReview} disabled={reviewSent} className="btn btn-l btn-primary">{t("review")}</button>}
        <Link href="/" className="btn btn-l btn-ghost" style={{ padding: "0 24px" }}>{t("another")}</Link>
      </div>
    </section>
  );
}
