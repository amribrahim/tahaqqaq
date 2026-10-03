"use client";

import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { pct } from "@/lib/format";
import { GLYPH_EN, STATE } from "@/lib/tokens";

export function StatusBanner({ r }: { r: Report }) {
  const t = useTranslations("result");
  const s = useTranslations("states");
  const { lang } = useLang();
  const st = STATE[r.state];
  const conf = r.state === "referral" ? 0 : r.confidence;
  const grade = r.grade ? (lang === "ar" ? r.grade.grade_ar : r.grade.grade_en || r.grade.grade_ar) : "";
  return (
    <div data-testid="status-banner" data-state={r.state} role="status" aria-live="polite" style={{ display: "flex", flexWrap: "wrap", gap: "20px 28px", alignItems: "stretch", padding: "clamp(20px,2.4vw,32px)", borderRadius: 20, background: st.surface, border: `1px solid ${st.border}` }}>
      <div style={{ flex: "999 1 400px", display: "flex", gap: 20, alignItems: "flex-start", minWidth: 0 }}>
        <div className="font-cairo" aria-hidden="true" style={{ flex: "none", width: 56, height: 56, borderRadius: 16, background: st.color, color: st.glyphInk, display: "grid", placeItems: "center", fontWeight: 800, fontSize: 28, lineHeight: 1 }}>
          {lang === "en" ? GLYPH_EN[r.state] : st.glyph}
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 0 }}>
          <span style={{ fontSize: 13, fontWeight: 700, color: st.color }}>{t("stateLbl")}</span>
          <h2 data-testid="state-label" className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(22px,2.6vw,32px)", lineHeight: 1.35, color: "#fff", textWrap: "balance" }}>{s(`${r.state}.label`, { grade })}</h2>
          <p style={{ margin: 0, fontSize: 16, lineHeight: 1.7, color: "#c9c3ff", textWrap: "pretty" }}>{s(`${r.state}.desc`, { grade })}</p>
        </div>
      </div>
      <div style={{ flex: "1 1 300px", display: "flex", flexDirection: "column", justifyContent: "center", gap: 12, padding: "18px 20px", borderRadius: 14, background: "rgba(13,16,53,0.5)", border: "1px solid rgba(201,195,255,0.12)" }}>
        <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
          <span style={{ fontSize: 14, fontWeight: 500, color: "#c9c3ff" }}>{t("conf")}</span>
          <span data-testid="confidence" className="font-cairo" style={{ fontWeight: 800, fontSize: 40, lineHeight: 1, color: "#fff" }}>{pct(conf, lang)}</span>
        </div>
        <div role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={conf} aria-label={t("conf")} style={{ position: "relative", height: 8, borderRadius: 99, background: "rgba(255,255,255,0.12)" }}>
          <div style={{ height: "100%", width: `${conf}%`, background: st.color, borderRadius: 99 }} />
          <span style={{ position: "absolute", top: -4, bottom: -4, insetInlineStart: `${r.threshold}%`, width: 2, borderRadius: 2, background: "rgba(255,255,255,0.55)" }} />
        </div>
        <span style={{ fontSize: 12, color: "#9d97d6" }}>{t("threshold")}</span>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6, color: "#e4e1ff", textWrap: "pretty" }}>{lang === "ar" ? r.reason_ar : r.reason_en}</p>
        {r.match_check && r.match_check.outcome !== "kept" && (
          <span data-testid="match-check" style={{ alignSelf: "flex-start", fontSize: 12, fontWeight: 700, padding: "4px 10px", borderRadius: 999, background: "rgba(124,108,240,0.25)", color: "#e4e1ff" }}>
            🤖 {r.match_check.outcome === "confirmed" ? t("checkConfirmed") : t("checkRejected")}
          </span>
        )}
      </div>
    </div>
  );
}
