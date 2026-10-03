"use client";

import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";
import { dorarFor, type DorarInfo, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { GRADE_CHIP, gradeFamily } from "@/lib/tokens";

/** Rulings of the scholars on the matched hadith, fetched live from الدرر السنية (the challenge's approved
 *  reference for hadith) and shown verbatim. Loads after the report so verification is never delayed. */
export function DorarCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const [info, setInfo] = useState<DorarInfo | null>(null);
  useEffect(() => {
    let alive = true;
    if (r.source) dorarFor(r.source.collection, r.source.number).then((x) => alive && setInfo(x)).catch(() => alive && setInfo({ available: false, cards: [] }));
    return () => { alive = false; };
  }, [r.source]);
  const link = info?.search_url || (r.grade?.url ?? r.source?.source_url ?? "https://dorar.net/hadith");
  return (
    <section className="card" data-testid="dorar-card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "10px 16px" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h3 className="card-title">{t("dorarTitle")}</h3>
          <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("dorarSub")}</span>
        </div>
        <a data-testid="dorar-link" href={link} target="_blank" rel="noreferrer" className="btn btn-s btn-secondary">{t("dorarOpen")} <span>↗</span></a>
      </header>
      {!info ? (
        <p style={{ margin: 0, fontSize: 14, color: "#5a5d80" }}>{t("dorarLoading")}</p>
      ) : !info.available ? (
        <p data-testid="dorar-unavailable" style={{ margin: 0, fontSize: 14, color: "#8a5300" }}>{t("dorarUnavailable")}</p>
      ) : (
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
          {info.cards.map((c, i) => {
            const chip = GRADE_CHIP[gradeFamily(c.grade)];
            return (
              <li key={i} data-testid="dorar-ruling" style={{ display: "flex", flexDirection: "column", gap: 6, padding: "12px 14px", borderRadius: 12, border: "1px solid #ebe9f5", background: i === 0 ? "#fbfaff" : "#fff" }}>
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <span className="font-cairo" style={{ padding: "3px 12px", borderRadius: 8, background: chip.bg, color: chip.fg, fontWeight: 800, fontSize: 15 }}>{c.grade.replace(/^\[|\]$/g, "")}</span>
                  <span style={{ fontSize: 14, fontWeight: 700 }}>{t("dorarScholar")}: {c.scholar}</span>
                  <span style={{ fontSize: 14, color: "#3d4066" }}>· {t("dorarBook")}: {c.book}{c.number ? ` · ${t("dorarNumber")} ${c.number}` : ""}</span>
                </div>
                {c.narrator && <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("dorarNarrator")}: {c.narrator}</span>}
                <p dir="rtl" style={{ margin: 0, fontSize: 15, lineHeight: 1.8, color: "#14173d" }} lang="ar">{c.text.length > 220 ? c.text.slice(0, 220) + "…" : c.text}</p>
              </li>
            );
          })}
        </ul>
      )}
      {lang === "en" && info?.available && <span style={{ fontSize: 12, color: "#8e90ad" }}>Rulings are quoted in Arabic as published.</span>}
    </section>
  );
}
