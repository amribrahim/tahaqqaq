"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";
import { ocr, VerifyError } from "@/lib/api";
import { useLang } from "@/lib/i18n";
import { num } from "@/lib/format";
import { newId, setPending } from "@/lib/session";

type Tab = "text" | "image" | "url";
const MAX = 2000;

export function VerifyCard({ text, setText, tab, setTab }: { text: string; setText: (t: string) => void; tab: Tab; setTab: (t: Tab) => void }) {
  const t = useTranslations("home");
  const tr = useTranslations("result");
  const { lang } = useLang();
  const router = useRouter();
  const [url, setUrl] = useState("");
  const [ocrState, setOcrState] = useState<"idle" | "running" | "done" | "error">("idle");
  const [ocrText, setOcrText] = useState("");
  const [ocrFull, setOcrFull] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const canSubmit = tab === "text" ? text.trim().length > 0 && text.length <= MAX
    : tab === "url" ? url.trim().length > 3
    : ocrState === "done" && ocrText.trim().length > 0;

  const submit = () => {
    if (!canSubmit) return;
    const id = newId();
    if (tab === "text") setPending(id, { text: text.trim(), via: "text" });
    else if (tab === "url") setPending(id, { url: url.trim(), via: "url" });
    else setPending(id, { text: ocrText.trim(), via: "image", extracted: ocrFull || ocrText });
    router.push(`/result/?id=${id}`);
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setErr("");
    if (file.size > 10 * 1024 * 1024) { setErr(tr("errOcr")); setOcrState("error"); return; }
    setOcrState("running");
    try {
      const r = await ocr(file);
      setOcrText(r.text);
      setOcrFull(r.full);
      setOcrState("done");
    } catch (e) {
      setErr(e instanceof VerifyError ? `${tr("errOcr")} — ${e.message}` : tr("errOcr"));
      setOcrState("error");
    }
  };

  const tabStyle = (k: Tab) => ({
    flex: "1 1 0", maxWidth: 180, height: 58, border: 0, borderBottom: `3px solid ${tab === k ? "#7c6cf0" : "transparent"}`, marginBottom: -1,
    background: "transparent", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
    fontSize: 16, fontWeight: tab === k ? 700 : 500, color: tab === k ? "#4f3fd0" : "#5a5d80",
  } as const);
  const meta = { fontFamily: "var(--font-tajawal)", fontSize: 11, fontWeight: 500, padding: "2px 7px", borderRadius: 6, background: "#f1effc", color: "#5a5d80" } as const;

  return (
    <section data-testid="verify-card" style={{ background: "#fff", borderRadius: 24, boxShadow: "var(--shadow-raised)", overflow: "hidden" }}>
      <div role="tablist" style={{ display: "flex", gap: 4, padding: "0 clamp(8px,2vw,24px)", borderBottom: "1px solid #ebe9f5" }}>
        <button role="tab" data-testid="tab-text" aria-selected={tab === "text"} className="font-cairo" onClick={() => setTab("text")} style={tabStyle("text")}>{t("tabText")}<span style={meta}>{t("tabTextMeta")}</span></button>
        <button role="tab" data-testid="tab-image" aria-selected={tab === "image"} className="font-cairo" onClick={() => setTab("image")} style={tabStyle("image")}>{t("tabImage")}<span style={meta}>{t("tabImageMeta")}</span></button>
        <button role="tab" data-testid="tab-url" aria-selected={tab === "url"} className="font-cairo" onClick={() => setTab("url")} style={tabStyle("url")}>{t("tabUrl")}<span style={meta}>{t("tabUrlMeta")}</span></button>
      </div>

      {tab === "text" && (
        <div style={{ padding: "clamp(16px,2vw,24px)", display: "flex", flexDirection: "column", gap: 12 }}>
          <textarea data-testid="input-text" aria-label={t("placeholder")} dir="auto" value={text} onChange={(e) => setText(e.target.value.slice(0, MAX + 200))} placeholder={t("placeholder")} className="field"
            onKeyDown={(e) => { if ((e.metaKey || e.ctrlKey) && e.key === "Enter") submit(); }}
            style={{ minHeight: 168, resize: "vertical", padding: "18px 20px", fontSize: 19, lineHeight: 1.8 }} />
          <div style={{ display: "flex", justifyContent: "space-between", gap: 12, flexWrap: "wrap", fontSize: 13, color: "#5a5d80" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 6, height: 6, borderRadius: "50%", background: "#3ee6c0" }} />{t("langAuto")}</span>
            <span data-testid="counter" style={{ color: text.length > MAX ? "#a8324a" : undefined }}>{num(text.length, lang)} / {t("counterMax")}</span>
          </div>
        </div>
      )}

      {tab === "image" && (
        <div style={{ padding: "clamp(16px,2vw,24px)", display: "flex", flexDirection: "column", gap: 12 }}>
          <div onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]); }}
            style={{ minHeight: 200, border: "2px dashed #cfc9f5", borderRadius: 18, background: "#faf9ff", display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 10, padding: "28px 20px", textAlign: "center" }}>
            <span style={{ width: 52, height: 52, borderRadius: 16, background: "#ecebfe", color: "#4f3fd0", display: "grid", placeItems: "center", fontSize: 24, fontWeight: 700 }}>↑</span>
            <span className="font-cairo" style={{ fontWeight: 700, fontSize: 17 }}>{t("dropTitle")}</span>
            <span style={{ fontSize: 14, lineHeight: 1.6, color: "#5a5d80" }}>{t("dropHelp")}</span>
            <input ref={fileRef} data-testid="input-file" type="file" accept="image/png,image/jpeg" hidden onChange={(e) => onFile(e.target.files?.[0])} />
            <button className="btn btn-m btn-secondary" style={{ marginTop: 6 }} onClick={() => fileRef.current?.click()} disabled={ocrState === "running"}>
              {ocrState === "running" ? t("ocrRunning") : t("choose")}
            </button>
          </div>
          {ocrState === "done" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <span className="label">{t("ocrDone")}</span>
              <textarea data-testid="ocr-text" dir="auto" value={ocrText} onChange={(e) => setOcrText(e.target.value)} className="field"
                rows={Math.min(14, Math.max(5, Math.ceil(ocrText.length / 80) + 1))}
                style={{ minHeight: 160, padding: "14px 16px", fontSize: 18, lineHeight: 1.9, resize: "vertical" }} />
            </div>
          )}
          {ocrState === "error" && <div data-testid="ocr-error"><ErrorRow text={err} /></div>}
        </div>
      )}

      {tab === "url" && (
        <div style={{ padding: "clamp(16px,2vw,24px)", display: "flex", flexDirection: "column", gap: 12 }}>
          <label style={{ fontSize: 14, fontWeight: 500, color: "#5a5d80" }}>{t("urlLabel")}</label>
          <div dir="ltr" className="field" style={{ display: "flex", alignItems: "center", gap: 8, height: 60, padding: "0 18px" }}>
            <span style={{ fontFamily: "ui-monospace, Menlo, monospace", fontSize: 15, color: "#8e90ad" }}>{url.startsWith("http://") ? "" : "https://"}</span>
            <input data-testid="input-url" aria-label={t("urlLabel")} type="text" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value.replace(/^https:\/\//, ""))} placeholder={t("urlPlaceholder")}
              onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
              style={{ flex: 1, minWidth: 0, border: 0, background: "transparent", outline: "none", fontFamily: "var(--font-tajawal)", fontSize: 17, color: "#14173d" }} />
          </div>
          <span style={{ fontSize: 13, lineHeight: 1.6, color: "#5a5d80" }}>{t("urlHelp")}</span>
        </div>
      )}

      <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "16px 24px", padding: "18px clamp(16px,2vw,24px)", background: "#faf9fe", borderTop: "1px solid #ebe9f5" }}>
        <div style={{ flex: "999 1 340px", display: "flex", flexDirection: "column", gap: 6, fontSize: 14, lineHeight: 1.6, color: "#3d4066" }}>
          <span style={{ display: "flex", gap: 8 }}><span style={{ flex: "none", color: "#087a62", fontWeight: 800 }}>✓</span>{t("does")}</span>
          <span style={{ display: "flex", gap: 8 }}><span style={{ flex: "none", color: "#a8324a", fontWeight: 800 }}>✕</span>{t("doesnt")}</span>
        </div>
        <button data-testid="verify-btn" onClick={submit} disabled={!canSubmit} className="btn btn-primary" style={{ flex: "1 0 160px", height: 56, padding: "0 36px", borderRadius: 14, fontSize: 18, gap: 10 }}>
          {t("verify")}<span>{lang === "ar" ? "←" : "→"}</span>
        </button>
      </div>
    </section>
  );
}

function ErrorRow({ text }: { text: string }) {
  return (
    <div style={{ display: "flex", gap: 10, alignItems: "center", padding: "12px 16px", borderRadius: 12, border: "1px solid #f6dde2", background: "#fffafb", color: "#a8324a", fontSize: 14 }}>
      <span style={{ flex: "none", width: 28, height: 28, borderRadius: 8, background: "#fde4e8", display: "grid", placeItems: "center", fontWeight: 800 }}>!</span>{text}
    </div>
  );
}
