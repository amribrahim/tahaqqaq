/** Session-only history (sessionStorage). Nothing leaves the browser. */
import type { Report } from "./api";
import type { State } from "./tokens";

export type Pending = { text?: string; url?: string; via: "text" | "image" | "url"; extracted?: string };
export type HistoryRow = { id: string; text: string; via: "text" | "image" | "url"; lang: "ar" | "en"; state: State; grade: string; closest: boolean; time: string };

export const HISTORY_KEY = "tahqaq.history";
const H = HISTORY_KEY;
const ss = () => (typeof window === "undefined" ? null : window.sessionStorage);

export function newId(): string { return Math.random().toString(36).slice(2, 10) + Date.now().toString(36).slice(-4); }

export function setPending(id: string, p: Pending) { ss()?.setItem(`tahqaq.pending.${id}`, JSON.stringify(p)); }
export function getPending(id: string): Pending | null { const v = ss()?.getItem(`tahqaq.pending.${id}`); return v ? JSON.parse(v) : null; }
export function setReport(id: string, r: Report) { ss()?.setItem(`tahqaq.report.${id}`, JSON.stringify(r)); }
export function getReport(id: string): Report | null { const v = ss()?.getItem(`tahqaq.report.${id}`); return v ? JSON.parse(v) : null; }

export function history(): HistoryRow[] { try { return JSON.parse(ss()?.getItem(H) || "[]"); } catch { return []; } }

export function addHistory(r: Report) {
  const rows = history().filter((x) => x.id !== r.id);
  const ayah = r.source?.kind === "quran" ? r.source.number.split(":")[1].replace(/\d/g, (d) => "٠١٢٣٤٥٦٧٨٩"[Number(d)]) : "";
  const grade = r.grade ? (r.source?.kind === "quran" ? `آية · ${r.source!.chapter_ar.replace("سورة ", "")} ${ayah}` : r.grade.grade_ar) : "—";
  rows.unshift({ id: r.id, text: r.input_text, via: r.via, lang: r.input_lang, state: r.state, grade, closest: r.closest_only, time: r.created_at });
  ss()?.setItem(H, JSON.stringify(rows.slice(0, 50)));
}

export function clearHistory() {
  const s = ss(); if (!s) return;
  const keys = Object.keys(s).filter((k) => k.startsWith("tahqaq."));
  keys.forEach((k) => s.removeItem(k));
}
