"use client";

import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { GRADE_CHIP, gradeFamily } from "@/lib/tokens";

/** The same text recorded in other books (or under other numbers), each with its own recorded ruling. */
export function NarrationsCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  if (!r.narrations?.length) return null;
  return (
    <section className="card" data-testid="narrations-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <header style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <h3 className="card-title">{t("narrTitle")}</h3>
        <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("narrSub")}</span>
      </header>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column" }}>
        {r.narrations.map((n, i) => {
          const chip = GRADE_CHIP[gradeFamily(n.grade_ar)];
          const grade = lang === "ar" ? n.grade_ar : n.grade_en || n.grade_ar;
          const grader = lang === "ar" ? n.grader_ar : n.grader_en || n.grader_ar;
          return (
            <li key={`${n.collection}-${n.number}`} data-testid="narration" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 12px", padding: "12px 0", borderTop: i ? "1px solid #f0eef8" : "none" }}>
              <a href={n.source_url} target="_blank" rel="noreferrer" style={{ fontWeight: 700, fontSize: 15, color: "#14173d" }}>
                {lang === "ar" ? n.book_ar : n.book_en} · {n.number} <span aria-hidden="true">↗</span>
              </a>
              {grade && <span className="font-cairo" style={{ padding: "2px 10px", borderRadius: 8, background: chip.bg, color: chip.fg, fontWeight: 800, fontSize: 14 }}>{grade}</span>}
              {grader && <span style={{ fontSize: 13, color: "#5a5d80" }}>{grader}</span>}
              <span style={{ marginInlineStart: "auto", fontSize: 13, color: "#5a5d80" }}>{t("narrSimilarity", { n: n.similarity })}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
