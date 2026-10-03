"use client";

import { useTranslations } from "next-intl";
import type { Issue, Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { Tokens } from "./Diff";

export function IssueList({ issues }: { issues: Issue[] }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  return (
    <ol data-testid="issues" style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
      {issues.map((is, i) => (
        <li key={i} style={{ display: "flex", gap: 12, alignItems: "flex-start", padding: "14px 16px", borderRadius: 12, border: "1px solid #ebe9f5" }}>
          <span style={{ flex: "none", padding: "3px 10px", borderRadius: 999, fontSize: 12, fontWeight: 700, background: is.severity === "high" ? "#fde4e8" : "#f1eff4", color: is.severity === "high" ? "#a8324a" : "#5a5d80" }}>
            {is.severity === "high" ? t("sevHigh") : t("sevLow")}
          </span>
          <span dir={lang === "ar" ? "rtl" : "ltr"} style={{ fontSize: 15, lineHeight: 1.7, textWrap: "pretty" }}>{lang === "ar" ? is.text_ar : is.text_en}</span>
        </li>
      ))}
    </ol>
  );
}

export function TranslationCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const tr = r.translation!;
  const flag = tr.needs_fix
    ? { bg: "#fdf0d9", fg: "#8a5300", dot: "#f2a93b", label: t("transFlag") }
    : { bg: "#dcfaf1", fg: "#087a62", dot: "#3ee6c0", label: t("transOk") };
  return (
    <section className="card" data-testid="translation-card" style={{ display: "flex", flexDirection: "column", gap: 20 }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "10px 16px" }}>
        <h3 className="card-title">{t("transTitle")}</h3>
        <span className="chip" style={{ background: flag.bg, color: flag.fg }}><span className="dot" style={{ background: flag.dot }} />{flag.label}</span>
      </header>
      <div className="panel" style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <span className="label">{t("original")}</span>
        <p dir="rtl" style={{ margin: 0, fontSize: 24, lineHeight: 1.9, fontWeight: 500 }}>{tr.original_ar}</p>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16 }}>
        <div className="panel-red" style={{ flex: "1 1 260px", display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="label" style={{ color: "#a8324a" }}>{t("yours")}</span>
          <p dir="ltr" style={{ margin: 0, fontSize: 18, lineHeight: 1.8, textAlign: "left" }}><Tokens tokens={tr.user_tokens} /></p>
        </div>
        <div className="panel-mint" style={{ flex: "1 1 260px", display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="label" style={{ color: "#087a62" }}>{t("approved")}</span>
          <p dir="ltr" style={{ margin: 0, fontSize: 18, lineHeight: 1.8, textAlign: "left" }}><Tokens tokens={tr.approved_tokens} /></p>
        </div>
      </div>
      {tr.issues.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          <h4 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 16 }}>{t("issues")}</h4>
          <IssueList issues={tr.issues} />
        </div>
      )}
    </section>
  );
}

export function TermsCard({ terms }: { terms: Issue[] }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  return (
    <section className="card" style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <header style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <h3 className="card-title">{t("termsTitle")}</h3>
        <span style={{ fontSize: 13, color: "#5a5d80" }}>{t("termsSub")}</span>
      </header>
      <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: 10 }}>
        {terms.map((g, i) => (
          <li key={i} style={{ display: "flex", flexDirection: "column", gap: 6, padding: "14px 16px", borderRadius: 12, border: "1px solid #ebe9f5" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
              <span className="font-cairo" style={{ fontWeight: 800, fontSize: 18 }}>{g.term_ar}</span>
              <span style={{ padding: "2px 10px", borderRadius: 8, background: "#f1effc", color: "#4f3fd0", fontSize: 13, fontWeight: 700 }} dir="ltr">{g.term_en}</span>
              {g.literal.length > 0 && (
                <span style={{ padding: "2px 10px", borderRadius: 999, background: "#fde4e8", color: "#a8324a", fontSize: 12, fontWeight: 700 }} dir="ltr">{t("termAvoid")}: {g.literal.join(", ")}</span>
              )}
            </div>
            <span dir={lang === "ar" ? "rtl" : "ltr"} style={{ fontSize: 15, lineHeight: 1.7, color: "#3d4066" }}>{lang === "ar" ? g.meaning_ar : g.meaning_en}</span>
            {g.literal.length > 0 && <span dir={lang === "ar" ? "rtl" : "ltr"} style={{ fontSize: 14, lineHeight: 1.7, color: "#5a5d80" }}>{lang === "ar" ? g.text_ar : g.text_en}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}
