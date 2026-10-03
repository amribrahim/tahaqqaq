/** State and grade colour tokens straight from design/README.md. */
export type State = "verified" | "partial" | "uncertain" | "abstain" | "referral" | "unreliable";

export const STATE = {
  verified: { color: "#3ee6c0", glyph: "✓", glyphInk: "#0d1035", surface: "rgba(62,230,192,0.08)", border: "rgba(62,230,192,0.45)", chipBg: "#dcfaf1", chipFg: "#087a62", dot: "#3ee6c0" },
  partial: { color: "#7c6cf0", glyph: "≈", glyphInk: "#ffffff", surface: "rgba(124,108,240,0.14)", border: "rgba(124,108,240,0.6)", chipBg: "#ecebfe", chipFg: "#4f3fd0", dot: "#7c6cf0" },
  uncertain: { color: "#f2a93b", glyph: "؟", glyphInk: "#0d1035", surface: "rgba(242,169,59,0.08)", border: "rgba(242,169,59,0.5)", chipBg: "#fdf0d9", chipFg: "#8a5300", dot: "#f2a93b" },
  abstain: { color: "#f07a8a", glyph: "—", glyphInk: "#0d1035", surface: "rgba(255,255,255,0.04)", border: "rgba(240,122,138,0.55)", chipBg: "#f1eff4", chipFg: "#a8324a", dot: "#e7647a" },
  // matched text whose recorded ruling is fabricated/weak: red family, never a green check
  unreliable: { color: "#f07a8a", glyph: "✕", glyphInk: "#0d1035", surface: "rgba(240,122,138,0.10)", border: "rgba(240,122,138,0.55)", chipBg: "#fde4e8", chipFg: "#a8324a", dot: "#e7647a" },
  // 5th state (not in the original design): teal family from the tokens
  referral: { color: "#5fd0ec", glyph: "↗", glyphInk: "#0d1035", surface: "rgba(95,208,236,0.10)", border: "rgba(95,208,236,0.5)", chipBg: "#ddf2f8", chipFg: "#0f6a85", dot: "#5fd0ec" },
} as const;

export type GradeFamily = "sahih" | "hasan" | "daif" | "mawdu" | "ayah" | "other";

export const GRADE_CHIP: Record<GradeFamily, { bg: string; fg: string }> = {
  sahih: { bg: "#dcfaf1", fg: "#087a62" },
  hasan: { bg: "#ddf2f8", fg: "#0f6a85" },
  daif: { bg: "#fdf0d9", fg: "#8a5300" },
  mawdu: { bg: "#fde4e8", fg: "#a8324a" },
  ayah: { bg: "#fdf0d9", fg: "#8a5300" },
  other: { bg: "#f1eff4", fg: "#3d4066" },
};

/** Classify a verbatim ruling into a colour family (display only; the text itself is never changed). */
export function gradeFamily(gradeAr: string): GradeFamily {
  const g = gradeAr || "";
  if (/آية/.test(g)) return "ayah";
  if (/موضوع|باطل|لا أصل|لا اصل|منكر|ليس|لم أجد|لا يصح|كذب|مكذوب/.test(g)) return "mawdu";
  if (/ضعيف/.test(g)) return "daif";
  if (/صحيح/.test(g) && !/ضعيف/.test(g)) return "sahih";
  if (/حسن/.test(g)) return "hasan";
  return "other";
}

export const GLYPH_EN: Record<State, string> = { verified: "✓", partial: "≈", uncertain: "?", abstain: "—", referral: "↗", unreliable: "✕" };
