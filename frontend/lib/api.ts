import type { Lang } from "./i18n";
import type { State } from "./tokens";

export const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type Token = { t: string; k: "eq" | "del" | "ins" };
export type Grade = { grader_ar: string; grader_en: string; grade_ar: string; grade_en: string; source_ar: string; source_en: string; number: string; url: string };
export type Source = {
  kind: string; collection: string; book_ar: string; book_en: string; number: string; chapter_ar: string; chapter_en: string;
  type_ar: string; type_en: string; text_ar: string; matn_ar: string; text_en: string; text_en_quote: string; source_url: string; alt_url: string; note_ar: string; note_en: string;
};
export type Candidate = { rank: number; text_ar: string; text_en: string; book_ar: string; book_en: string; number: string; kind: string; confidence: number; lexical: number; semantic: number; source_url: string; accepted: boolean };
export type Issue = { severity: "high" | "low"; text_ar: string; text_en: string; term_ar: string; term_en: string; meaning_ar: string; meaning_en: string; literal: string[]; source_url: string };
export type Segment = { text: string; type: string; origin: "ai" | "rules"; confidence: number; state: State; book_ar: string; book_en: string; number: string; kind: string; source_url: string };
export type Narration = { collection: string; book_ar: string; book_en: string; number: string; grade_ar: string; grade_en: string; grader_ar: string; grader_en: string; similarity: number; source_url: string };
export type MatchCheck = { model: string; outcome: "confirmed" | "rejected" | "kept"; checked: number };
export type Translation = { original_ar: string; user_tokens: Token[]; approved_tokens: Token[]; approved_text: string; needs_fix: boolean; issues: Issue[] };
export type Report = {
  id: string; state: State; confidence: number; threshold: number; match_level: string; reason_ar: string; reason_en: string; input_text: string; input_lang: "ar" | "en";
  via: "text" | "image" | "url"; extracted_text: string; source: Source | null; grade: Grade | null; grades: Grade[]; closest_only: boolean;
  diff_input: Token[]; diff_source: Token[]; translation: Translation | null; glossary_terms: Issue[]; quran_note: { ar: string; en: string } | null;
  candidates: Candidate[]; narrations: Narration[]; match_check: MatchCheck | null; segments: Segment[]; cleaned_text: string; extraction_model: string | null; machine_translation: { language: string; english: string; model: string } | null; ai_explanation: string | null; ai_model: string | null; created_at: string; timings_ms: Record<string, number>;
  server_id?: string;  // the API's id (r.id is replaced by the session id in the URL)
};
export type ApiError = { code: string; message: string };

export class VerifyError extends Error {
  code: string;
  constructor(code: string, message: string) { super(message); this.code = code; }
}

async function errorOf(res: Response): Promise<VerifyError> {
  try {
    const j = await res.json();
    const d = j.detail ?? j;
    return new VerifyError(d.code ?? "sources_unreachable", d.message ?? res.statusText);
  } catch {
    return new VerifyError("sources_unreachable", res.statusText);
  }
}

/** Wait for the API to answer /health (cold starts on free hosting can take up to a minute). */
export async function waitForApi(maxMs = 75000): Promise<boolean> {
  const t0 = Date.now();
  while (Date.now() - t0 < maxMs) {
    try {
      const r = await fetch(`${API}/health`, { cache: "no-store" });
      if (r.ok) return true;
    } catch {}
    await new Promise((r) => setTimeout(r, 2500));
  }
  return false;
}

async function fetchWithRetry(input: string, init: RequestInit, tries = 2): Promise<Response> {
  let last: unknown;
  for (let i = 0; i < tries; i++) {
    try {
      return await fetch(input, init);
    } catch (e) {
      last = e;  // network error (API restarting, cold start): wait for /health, then retry once
      await waitForApi();
    }
  }
  throw last;
}

/** POST /api/verify/stream and relay progress (step 0..3) then the final report. */
export async function verifyStream(
  body: { text?: string; url?: string; lang: Lang; via?: "text" | "image" | "url" },
  onStep: (step: number) => void,
  signal?: AbortSignal,
): Promise<Report> {
  let explain = true;
  try { explain = localStorage.getItem("tahqaq.explain") !== "0"; } catch {}
  const res = await fetchWithRetry(`${API}/api/verify/stream`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ...body, explain }), signal,
  });
  if (!res.ok || !res.body) throw await errorOf(res);
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let result: Report | null = null;
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx: number;
    while ((idx = buf.indexOf("\n\n")) >= 0) {
      const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
      let ev = "message", data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (!data) continue;
      const parsed = JSON.parse(data);
      if (ev === "progress") onStep(parsed.step);
      else if (ev === "result") result = parsed as Report;
      else if (ev === "error") throw new VerifyError(parsed.code, parsed.message);
    }
  }
  if (!result) throw new VerifyError("sources_unreachable", "no result");
  return result;
}

export async function ocr(file: File): Promise<{ text: string; full: string; lang: "ar" | "en" }> {
  const fd = new FormData();
  fd.append("image", file);
  try { fd.append("ai", localStorage.getItem("tahqaq.explain") === "0" ? "0" : "1"); } catch {}
  const res = await fetchWithRetry(`${API}/api/ocr`, { method: "POST", body: fd });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

export async function requestReview(report: Report, note = ""): Promise<{ accepted: boolean; forwarded: boolean }> {
  const res = await fetch(`${API}/api/review`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: report.id, text: report.input_text, state: report.state, note }),
  });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

/** The report as a PDF for a review request: the server prints the result page with the report it produced (never
 *  one sent by the browser), the same document as "export PDF", and keeps it behind a private link for `retain_days`.
 *  The name and email are not sent to the server: they go to the contact form only. */
export async function createReviewPdf(report: Report, lang: string): Promise<{ token: string; path: string; retain_days: number; report_id: string; state: State; confidence: number }> {
  const res = await fetch(`${API}/api/review/pdf`, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ report_id: report.server_id || report.id, text: report.input_text, lang, tz: Intl.DateTimeFormat().resolvedOptions().timeZone }),
  });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

/** Public form key of the site's Web3Forms contact form (meant to be in the page; it can only send to the owner). */
export const WEB3FORMS_KEY = process.env.NEXT_PUBLIC_WEB3FORMS_KEY || "e4f68388-9a7c-4ede-a724-4c28f2b9762b";

/** Send the review request to the team's inbox through the contact form. Web3Forms' free plan takes browser
 *  submissions only and no attachments, so the message carries the PDF link. */
export async function sendReviewForm(f: { name: string; email: string; subject: string; message: string; botcheck: boolean }): Promise<void> {
  let ok = false;
  try {
    const res = await fetch("https://api.web3forms.com/submit", {
      method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ access_key: WEB3FORMS_KEY, from_name: "Tahaqqaq", ...f }),
    });
    ok = res.ok && (await res.json()).success === true;
  } catch {}
  if (!ok) throw new VerifyError("form_failed", "contact form unavailable");
}

export async function health(): Promise<{ status: string; counts: Record<string, number>; embedder: string; llm: boolean; llm_provider: string; llm_chain: string[]; ocr: boolean } | null> {
  try {
    const res = await fetch(`${API}/health`, { cache: "no-store" });
    return res.ok ? res.json() : null;
  } catch { return null; }
}

export const EXPLAIN_LANGUAGES: { code: string; name: string; rtl?: boolean }[] = [
  { code: "ar", name: "العربية", rtl: true }, { code: "en", name: "English" }, { code: "fr", name: "Français" },
  { code: "ur", name: "اردو", rtl: true }, { code: "id", name: "Bahasa Indonesia" }, { code: "ms", name: "Bahasa Melayu" },
  { code: "tr", name: "Türkçe" }, { code: "fa", name: "فارسی", rtl: true }, { code: "bn", name: "বাংলা" }, { code: "hi", name: "हिन्दी" },
  { code: "de", name: "Deutsch" }, { code: "es", name: "Español" }, { code: "ru", name: "Русский" }, { code: "zh", name: "中文" },
  { code: "sw", name: "Kiswahili" }, { code: "so", name: "Soomaali" }, { code: "ha", name: "Hausa" }, { code: "am", name: "አማርኛ" },
  { code: "it", name: "Italiano" }, { code: "nl", name: "Nederlands" }, { code: "pt", name: "Português" }, { code: "ku", name: "Kurdî" },
  { code: "ps", name: "پښتو", rtl: true }, { code: "uz", name: "Oʻzbek" }, { code: "tg", name: "Тоҷикӣ" },
];

export type DorarCard = { text: string; grade: string; narrator: string; scholar: string; book: string; number: string; takhrij: string; xplain: string | null };
export type DorarInfo = { available: boolean; reason?: string; cards: DorarCard[]; best?: DorarCard | null; search_url?: string; sharh_available?: boolean };

/** Every scholar's ruling on the matched hadith, from الدرر السنية (the query is the source's wording, not the user's). */
export async function dorarFor(collection: string, number: string): Promise<DorarInfo> {
  const res = await fetch(`${API}/api/dorar?collection=${encodeURIComponent(collection)}&number=${encodeURIComponent(number)}`);
  if (!res.ok) return { available: false, cards: [] };
  return res.json();
}

export type ExplainResult = { explanation: string | null; model: string | null; grounding?: { source_ar: string; source_en: string; url: string } | null; reason?: string };

/** Re-word the explanation of a report in another language. Facts are taken from the report; nothing is stored. */
export async function explainIn(report: Report, lang: string, mode: "brief" | "extended" = "brief"): Promise<ExplainResult> {
  const body = {
    lang, mode, collection: report.source?.collection ?? "", number: report.source?.number ?? "", state: report.state, confidence: report.confidence, input_text: report.input_text,
    matched_text: report.source?.matn_ar ?? "", ruling: report.grade, quran_note: report.quran_note,
    // curated sayings carry an internal list number; the reference number is the ruling's (e.g. السلسلة الضعيفة 416)
    source: report.source ? { book: report.source.book_ar, number: (report.source.collection === "seed" ? report.grade?.number : "") || report.source.number, chapter: report.source.chapter_ar, type: report.source.type_ar } : null,
    translation_issues: report.translation?.issues.map((i) => i.text_ar) ?? [],
  };
  const res = await fetch(`${API}/api/explain`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

export type AssistantReply = {
  kind: "verify" | "report" | "tool" | "fatwa" | "generate" | "greeting" | "thanks" | "out_of_scope" | "unavailable";
  reply: string; lang: "ar" | "en"; report?: Report; sources?: string[]; model?: string;
};

/** POST /api/assistant: verification, the open report, or questions about the tool (nothing else). */
export async function askAssistant(message: string, lang: Lang, report: Report | null): Promise<AssistantReply> {
  const res = await fetchWithRetry(`${API}/api/assistant`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, lang, report }),
  });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

/** POST /api/stt: speech to text (Arabic and English). Unclear audio raises a VerifyError with a stt_* code. */
export async function transcribeAudio(audio: Blob, lang: Lang): Promise<{ text: string; heard?: string; corrected?: boolean; lang: "ar" | "en"; duration: number; confidence: number }> {
  const ext = audio.type.includes("mp4") ? "m4a" : audio.type.includes("ogg") ? "ogg" : audio.type.includes("wav") ? "wav" : "webm";
  const fd = new FormData();
  fd.append("audio", audio, `voice.${ext}`);
  fd.append("lang", lang);
  const res = await fetch(`${API}/api/stt`, { method: "POST", body: fd });
  if (!res.ok) throw await errorOf(res);
  return res.json();
}

/** The kind of a message without acting on it (the voice call confirms a heard hadith before verifying it). */
export async function routeAssistant(message: string, lang: Lang, report: Report | null): Promise<AssistantReply["kind"]> {
  const res = await fetch(`${API}/api/assistant`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message, lang, report, route_only: true }),
  });
  if (!res.ok) throw await errorOf(res);
  return (await res.json()).kind;
}
