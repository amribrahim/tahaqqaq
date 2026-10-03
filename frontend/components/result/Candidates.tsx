"use client";

import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { num, pct } from "@/lib/format";

export function Candidates({ r }: { r: Report }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const thr = r.threshold;
  return (
    <section className="card" data-testid="candidates" style={{ padding: "clamp(18px,2.2vw,24px)" }}>
      <header style={{ display: "flex", flexDirection: "column", gap: 4, marginBottom: 8 }}>
        <h3 className="card-title">{t("candTitle")}</h3>
        <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("candSub")}</span>
      </header>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column" }}>
        {r.candidates.map((c) => {
          const hi = c.confidence >= thr;
          return (
            <li key={c.rank} data-testid="candidate" style={{ display: "flex", gap: 12, padding: "14px 0", borderTop: "1px solid #f0eef8" }}>
              <span style={{ flex: "none", width: 26, height: 26, borderRadius: "50%", background: "#f1effc", color: "#4f3fd0", display: "grid", placeItems: "center", fontSize: 13, fontWeight: 700 }}>{num(c.rank, lang)}</span>
              <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 8 }}>
                {lang === "en" && c.text_en ? (
                  <p dir="ltr" style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: "#14173d", textAlign: "left" }}>{c.text_en}{c.text_en.length >= 220 ? "…" : ""}</p>
                ) : (
                  <p dir="rtl" style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: "#14173d" }}>{c.text_ar}{c.text_ar.length >= 220 ? "…" : ""}</p>
                )}
                <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8, flexWrap: "wrap" }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#5a5d80" }}>
                    <a href={c.source_url} target="_blank" rel="noreferrer" style={{ color: "#5a5d80" }}>{lang === "ar" ? c.book_ar : c.book_en} · {num(c.number, lang)}</a>
                    {c.accepted && <span style={{ padding: "2px 8px", borderRadius: 999, background: "#dcfaf1", color: "#087a62", fontSize: 11, fontWeight: 700 }}>{t("accepted")}</span>}
                  </span>
                  <span className="font-cairo" style={{ fontSize: 15, fontWeight: 800, color: hi ? "#4f3fd0" : "#5a5d80" }}>{pct(c.confidence, lang)}</span>
                </div>
                <div style={{ height: 4, borderRadius: 99, background: "#f0eef8" }}><div style={{ height: "100%", width: `${c.confidence}%`, borderRadius: 99, background: hi ? "#7c6cf0" : "#c4c1d6" }} /></div>
              </div>
            </li>
          );
        })}
        {r.candidates.length === 0 && <li style={{ padding: "14px 0", borderTop: "1px solid #f0eef8", fontSize: 14, color: "#5a5d80" }}>—</li>}
      </ol>
      <div style={{ paddingTop: 12, borderTop: "1px solid #f0eef8", fontSize: 12, color: "#5a5d80" }}>{t("threshold")}</div>
    </section>
  );
}
