"use client";

import { useTranslations } from "next-intl";
import type { Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { num } from "@/lib/format";
import { GRADE_CHIP, gradeFamily } from "@/lib/tokens";

export function GradeChip({ gradeAr, gradeEn, size = 18 }: { gradeAr: string; gradeEn: string; size?: number }) {
  const { lang } = useLang();
  const c = GRADE_CHIP[gradeFamily(gradeAr)];
  return (
    <span data-testid="grade-chip" className="font-cairo" style={{ alignSelf: "flex-start", padding: "4px 14px", borderRadius: 8, background: c.bg, color: c.fg, fontSize: size, fontWeight: 800, lineHeight: 1.6 }}>
      {lang === "ar" ? gradeAr : gradeEn || gradeAr}
    </span>
  );
}

export function GradeCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const s = r.source!;
  const g = r.grade;
  const L = (ar: string, en: string) => (lang === "ar" ? ar : en || ar);
  const cell = { background: "#fff", padding: "16px 18px", display: "flex", flexDirection: "column" as const, gap: 8 };
  const lbl = { fontSize: 13, color: "#5a5d80" };
  const val = { fontSize: 16, fontWeight: 700, lineHeight: 1.5 };
  const isQuran = s.kind === "quran";
  const numberText = isQuran ? num(s.number.split(":")[1], lang) : num(s.number, lang);
  return (
    <section className="card" data-testid="grade-card" style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "10px 16px" }}>
        <h3 className="card-title">{t("gradeTitle")}</h3>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {s.alt_url && <a href={s.alt_url} target="_blank" rel="noreferrer" className="btn btn-s btn-ghost">{t("viewAlt")}<span>↗</span></a>}
          <a data-testid="source-link" href={g?.url || s.source_url} target="_blank" rel="noreferrer" className="btn btn-s btn-secondary">{t("view")}<span>↗</span></a>
        </div>
      </header>
      {r.quran_note && (
        <div data-testid="quran-note" style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 16px", borderRadius: 12, background: "#fdf0d9", color: "#8a5300", fontSize: 14, fontWeight: 500 }}>
          <span style={{ flex: "none", width: 8, height: 8, borderRadius: "50%", background: "#f2a93b" }} />{lang === "ar" ? r.quran_note.ar : r.quran_note.en}
        </div>
      )}
      {r.closest_only && (
        <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 16px", borderRadius: 12, background: "#fdf0d9", color: "#8a5300", fontSize: 14, fontWeight: 500 }}>
          <span style={{ flex: "none", width: 8, height: 8, borderRadius: "50%", background: "#f2a93b" }} />{t("closestNote")}
        </div>
      )}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%,200px),1fr))", gap: 1, background: "#ebe9f5", border: "1px solid #ebe9f5", borderRadius: 14, overflow: "hidden" }}>
        <div style={cell}><span style={lbl}>{t("type")}</span><span style={{ alignSelf: "flex-start", padding: "4px 12px", borderRadius: 8, background: "#f1effc", color: "#4f3fd0", fontSize: 14, fontWeight: 700 }}>{L(s.type_ar, s.type_en)}</span></div>
        <div style={cell}><span style={lbl}>{t("grade")}</span>{g ? <GradeChip gradeAr={g.grade_ar} gradeEn={g.grade_en} /> : <span style={{ fontSize: 14, color: "#8a5300" }}>{t("noRuling")}</span>}</div>
        <div style={cell}><span style={lbl}>{t("grader")}</span><span data-testid="grader" style={val}>{g ? L(g.grader_ar, g.grader_en) : "—"}</span></div>
        <div style={cell}><span style={lbl}>{t("source")}</span><span style={val}>{g ? L(g.source_ar, g.source_en) : L(s.book_ar, s.book_en)}</span></div>
        <div style={cell}><span style={lbl}>{t("chapter")}</span><span style={val}>{L(s.chapter_ar, s.chapter_en) || (isQuran ? L(s.chapter_ar, s.chapter_en) : L(s.book_ar, s.book_en))}</span></div>
        <div style={cell}><span style={lbl}>{t("number")}</span><span data-testid="number" className="font-cairo" style={{ fontSize: 22, fontWeight: 800 }}>{numberText}</span></div>
      </div>
      {r.grades.length > 1 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <span className="label">{t("otherGrades")}</span>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: 8 }}>
            {r.grades.slice(1).map((x, i) => (
              <li key={i} style={{ display: "flex", alignItems: "center", gap: 8, padding: "6px 12px", borderRadius: 10, border: "1px solid #ebe9f5", fontSize: 14 }}>
                <GradeChip gradeAr={x.grade_ar} gradeEn={x.grade_en} size={14} />
                <span style={{ color: "#3d4066" }}>{L(x.grader_ar, x.grader_en)}{x.source_ar && x.source_ar !== (g?.source_ar ?? "") ? ` · ${L(x.source_ar, x.source_en)}` : ""}{x.number && x.number !== s.number ? ` ${num(x.number, lang)}` : ""}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {lang === "en" && s.text_en_quote && r.input_lang === "ar" && (
        <div className="panel" style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="label">{t("approved")}</span>
          <p dir="ltr" style={{ margin: 0, fontSize: 16, lineHeight: 1.7, textAlign: "left" }}>{s.text_en_quote}</p>
        </div>
      )}
      {(s.note_ar || s.note_en) && <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, color: "#3d4066" }}>{L(s.note_ar, s.note_en)}</p>}
    </section>
  );
}
