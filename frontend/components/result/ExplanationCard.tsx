"use client";

import { useTranslations } from "next-intl";
import { useEffect, useRef, useState } from "react";
import { EXPLAIN_LANGUAGES, explainIn, type Report } from "@/lib/api";
import { useLang } from "@/lib/i18n";

const PREF = "tahqaq.explainLang";
type Mode = "brief" | "extended";

/** The only LLM-generated text on the page. Visibly separated from quoted source text.
 *  Brief: relays the result in 2-4 sentences. Extended: meaning, vocabulary and lessons of the
 *  matched source text (never of the user's wording), with its own warning label.
 *  A dropdown re-words either mode in any listed language (no re-verification). */
export function ExplanationCard({ report, text, model }: { report: Report; text: string; model: string | null }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const [code, setCode] = useState<string>(lang);
  const [mode, setMode] = useState<Mode>("brief");
  const [cache, setCache] = useState<Record<string, { text: string; model: string | null; grounding?: { source_ar: string; source_en: string; url: string } | null }>>({ [`brief:${lang}`]: { text, model } });
  const [noSource, setNoSource] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const booted = useRef(false);

  const canExtend = !["abstain", "referral", "uncertain"].includes(report.state) && !!report.source?.matn_ar;
  const key = `${mode}:${code}`;
  const current = cache[key];

  const load = async (nextMode: Mode, nextCode: string) => {
    const k = `${nextMode}:${nextCode}`;
    setMode(nextMode); setCode(nextCode); setFailed(false);
    if (cache[k] || noSource[k]) return;
    setBusy(true);
    try {
      const r = await explainIn(report, nextCode, nextMode);
      if (r.explanation) setCache((c) => ({ ...c, [k]: { text: r.explanation!, model: r.model, grounding: r.grounding } }));
      else if (r.reason === "no_source") setNoSource((n) => ({ ...n, [k]: true }));
      else setFailed(true);
    } catch { setFailed(true); } finally { setBusy(false); }
  };

  useEffect(() => {
    if (booted.current) return;
    booted.current = true;
    let saved = "";
    try { saved = localStorage.getItem(PREF) || ""; } catch {}
    if (saved && saved !== lang && EXPLAIN_LANGUAGES.some((l) => l.code === saved)) void load("brief", saved);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const changeLang = (next: string) => { try { localStorage.setItem(PREF, next); } catch {} void load(mode, next); };
  const rtl = EXPLAIN_LANGUAGES.find((l) => l.code === code)?.rtl ?? false;
  const extended = mode === "extended";
  const paragraphs = (current?.text ?? "").split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
  const btn = (m: Mode, label: string, testId: string) => (
    <button key={m} data-testid={testId} onClick={() => void load(m, code)} disabled={busy}
      className="font-cairo" style={{ height: 32, padding: "0 12px", borderRadius: 999, border: "1.5px solid #d9d5f5", cursor: "pointer", fontWeight: 700, fontSize: 13,
        background: mode === m ? "#7c6cf0" : "#fff", color: mode === m ? "#fff" : "#4f3fd0" }}>{label}</button>
  );

  return (
    <section className="card" data-testid="ai-explanation" data-mode={mode} style={{ border: "1.5px dashed #cfc9f5", background: "#fbfaff", boxShadow: "none", display: "flex", flexDirection: "column", gap: 12 }}>
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          <span className="chip" style={{ background: extended ? "#fdf0d9" : "#ecebfe", color: extended ? "#8a5300" : "#4f3fd0" }}>🤖 {extended ? t("aiExtendedTitle") : t("aiTitle")}</span>
          <span style={{ fontSize: 12, color: "#5a5d80" }}>{extended ? t("aiExtendedNote") : t("aiSub")}{current?.model ? ` · ${current.model}` : ""}</span>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          {canExtend && <div style={{ display: "flex", gap: 6 }}>{btn("brief", t("aiBrief"), "ai-mode-brief")}{btn("extended", t("aiExtended"), "ai-mode-extended")}</div>}
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, color: "#5a5d80" }}>
            {t("aiLang")}
            <select data-testid="ai-lang" value={code} onChange={(e) => changeLang(e.target.value)} disabled={busy}
              style={{ height: 36, padding: "0 10px", borderRadius: 10, border: "1.5px solid #d9d5f5", background: "#fff", color: "#4f3fd0", fontFamily: "var(--font-cairo)", fontWeight: 700, fontSize: 14 }}>
              {EXPLAIN_LANGUAGES.map((l) => <option key={l.code} value={l.code}>{l.name}</option>)}
            </select>
          </label>
        </div>
      </header>
      {busy ? (
        <p style={{ margin: 0, fontSize: 15, color: "#5a5d80" }}>{t("aiGenerating")}</p>
      ) : noSource[key] ? (
        <p data-testid="ai-no-source" style={{ margin: 0, fontSize: 15, color: "#8a5300" }}>{t("aiNoSource")}</p>
      ) : failed || !current ? (
        <p style={{ margin: 0, fontSize: 15, color: "#a8324a" }}>{t("aiFailed")}</p>
      ) : (
        <div dir={rtl ? "rtl" : "ltr"} data-testid="ai-text" style={{ display: "flex", flexDirection: "column", gap: 10, textAlign: "start" }}>
          {paragraphs.map((p, i) => {
            const heading = /[:：]$/.test(p) && p.length <= 40;
            const m = heading ? null : p.match(/^([^\n:：]{2,40}[:：])\s*([\s\S]*)$/);
            return heading ? (
              <h4 key={i} className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 15, color: "#14173d" }}>{p}</h4>
            ) : (
              <p key={i} style={{ margin: 0, fontSize: 16, lineHeight: 1.8, color: "#3d4066", textWrap: "pretty" }}>
                {m ? <><strong style={{ color: "#14173d" }}>{m[1]}</strong> {m[2]}</> : p}
              </p>
            );
          })}
          {extended && current?.grounding && (
            <p data-testid="ai-grounding" style={{ margin: 0, fontSize: 14, color: "#5a5d80" }}>
              {t("aiGroundedFrom")} <a href={current.grounding.url} target="_blank" rel="noreferrer">{lang === "ar" ? current.grounding.source_ar : current.grounding.source_en} ↗</a>
            </p>
          )}
        </div>
      )}
    </section>
  );
}
