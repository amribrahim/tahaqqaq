import type { Lang } from "./i18n";

const AR_DIGITS = "٠١٢٣٤٥٦٧٨٩";

export function num(n: number | string, lang: Lang): string {
  const s = String(n);
  return lang === "ar" ? s.replace(/\d/g, (d) => AR_DIGITS[Number(d)]) : s;
}

export function pct(n: number, lang: Lang): string {
  return num(n, lang) + (lang === "ar" ? "٪" : "%");
}

export function timeOf(iso: string, lang: Lang): string {
  const d = new Date(iso);
  const s = d.toLocaleTimeString(lang === "ar" ? "ar-SA" : "en-US", { hour: "numeric", minute: "2-digit" });
  return lang === "ar" ? s.replace(/\d/g, (x) => AR_DIGITS[Number(x)]) : s;
}

export function isArabicText(t: string): boolean {
  const ar = (t.match(/[؀-ۿ]/g) || []).length;
  const la = (t.match(/[A-Za-z]/g) || []).length;
  return ar >= la;
}

export function pick<T extends Record<string, unknown>>(o: T, lang: Lang, key: string): string {
  return String(o[`${key}_${lang}`] ?? o[`${key}_ar`] ?? "");
}
