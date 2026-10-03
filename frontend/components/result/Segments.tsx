"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { num, pct } from "@/lib/format";
import { STATE } from "@/lib/tokens";

/** The quotations found in a long input / page / image, each with its own verification result.
 *  Extraction is AI-assisted (labelled); the matches and rulings come from the sources. */
export function SegmentsCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const s = useTranslations("states");
  const { lang } = useLang();
  const ai = r.segments.some((x) => x.origin === "ai");
  return (
    <section className="card" data-testid="segments-card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <header style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <h3 className="card-title">{t("segmentsTitle")}</h3>
          {ai && <span className="chip" style={{ background: "#ecebfe", color: "#4f3fd0", fontSize: 12 }}>🤖 {t("segAi")}{r.extraction_model ? ` · ${r.extraction_model}` : ""}</span>}
        </div>
        <span style={{ fontSize: 13, color: "#5a5d80" }}>{ai ? t("segmentsSub") : t("segmentsRules")}</span>
      </header>
      {r.cleaned_text && (
        <div className="panel" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="label">{t("cleanedText")}</span>
          <p dir="auto" style={{ margin: 0, fontSize: 16, lineHeight: 1.8, color: "#3d4066" }}>{r.cleaned_text}</p>
        </div>
      )}
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        {r.segments.map((sg, i) => {
          const st = STATE[sg.state];
          const matched = sg.confidence >= 50 && sg.number;
          return (
            <li key={i} data-testid="segment" style={{ display: "flex", flexDirection: "column", gap: 8, padding: "14px 16px", borderRadius: 12, border: "1px solid #ebe9f5" }}>
              <p dir="auto" style={{ margin: 0, fontSize: 17, lineHeight: 1.8, fontWeight: 500 }}>{sg.text}</p>
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap", fontSize: 13, color: "#5a5d80" }}>
                <span className="chip" style={{ background: st.chipBg, color: st.chipFg, fontSize: 12 }}><span className="dot" style={{ background: st.dot }} />{matched ? s(`${sg.state}.label`, { grade: "" }) : t("segNoMatch")}</span>
                {matched && <span>{lang === "ar" ? sg.book_ar : sg.book_en} · {num(sg.number, lang)}</span>}
                <span className="font-cairo" style={{ fontWeight: 800, color: sg.confidence >= r.threshold ? "#4f3fd0" : "#5a5d80" }}>{pct(sg.confidence, lang)}</span>
                <span style={{ padding: "2px 8px", borderRadius: 999, background: "#f1eff4", fontSize: 11, fontWeight: 700 }}>{sg.origin === "ai" ? t("segAi") : t("segRules")}</span>
                <Link href={`/result/?id=${r.id}-s${i}&text=${encodeURIComponent(sg.text)}`} className="btn btn-ghost btn-s" style={{ marginInlineStart: "auto", height: 32, fontSize: 13 }}>{t("segVerify")} {lang === "ar" ? "←" : "→"}</Link>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
