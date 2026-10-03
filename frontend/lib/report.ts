import type { Report } from "./api";
import type { Lang } from "./i18n";

/** Plain-text report for the clipboard. */
export function reportText(r: Report, lang: Lang, labels: { header: string; state: string; stateLabel?: string; conf: string; input: string; correct: string; grade: string; source: string; link: string; note: string }): string {
  const L = (ar: string, en: string) => (lang === "ar" ? ar : en);
  const lines = [labels.header, "", `${labels.state}: ${labels.stateLabel ?? ""}`.trim()];
  lines.push(`${labels.conf}: ${r.confidence}%`);
  lines.push(`${labels.input}: ${r.input_text}`);
  if (r.source) {
    lines.push(`${labels.correct}: ${r.source.matn_ar}`);
    if (r.grade) lines.push(`${labels.grade}: ${L(r.grade.grade_ar, r.grade.grade_en)} — ${L(r.grade.grader_ar, r.grade.grader_en)}`);
    lines.push(`${labels.source}: ${L(r.source.book_ar, r.source.book_en)} · ${L(r.source.chapter_ar, r.source.chapter_en)} · ${r.source.number}`);
    lines.push(`${labels.link}: ${r.source.source_url}`);
  }
  lines.push("", labels.note);
  return lines.join("\n");
}
