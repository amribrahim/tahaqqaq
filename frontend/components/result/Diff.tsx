"use client";

import { useTranslations } from "next-intl";
import type { Report, Token } from "@/lib/api";
import { useLang } from "@/lib/i18n";

export function Tokens({ tokens }: { tokens: Token[] }) {
  return (
    <>
      {tokens.map((k, i) => (
        <span key={i} className={k.k === "del" ? "tok-del" : k.k === "ins" ? "tok-ins" : undefined}>{k.t}</span>
      ))}
    </>
  );
}

export function Legend() {
  const t = useTranslations("result");
  return (
    <div style={{ display: "flex", gap: 16, fontSize: 13, color: "#5a5d80" }}>
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 14, height: 10, borderRadius: 3, background: "#fde4e8", borderBottom: "2px solid #e7647a" }} />{t("legDel")}</span>
      <span style={{ display: "flex", alignItems: "center", gap: 6 }}><span style={{ width: 14, height: 10, borderRadius: 3, background: "#d6f8ee", borderBottom: "2px solid #3ee6c0" }} />{t("legIns")}</span>
    </div>
  );
}

export function DiffCard({ r }: { r: Report }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const en = lang === "en" && r.source?.text_en_quote ? r.source.text_en_quote : "";
  return (
    <section className="card" data-testid="diff-card">
      <header style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "10px 16px" }}>
        <h3 className="card-title">{t("diffTitle")}</h3>
        <Legend />
      </header>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 16, marginTop: 20 }}>
        <div className="panel" style={{ flex: "1 1 260px" }}>
          <span className="label">{t("input")}</span>
          <p dir="rtl" style={{ margin: "10px 0 0", fontSize: 22, lineHeight: 2.1, fontWeight: 500 }}><Tokens tokens={r.diff_input} /></p>
        </div>
        <div className="panel-mint" style={{ flex: "1 1 260px" }}>
          <span className="label" style={{ color: "#087a62" }}>{r.state === "unreliable" ? t("asRecorded") : r.closest_only ? t("closest") : t("correct")}</span>
          <p dir="rtl" style={{ margin: "10px 0 0", fontSize: 22, lineHeight: 2.1, fontWeight: 500 }}><Tokens tokens={r.diff_source} /></p>
          {en && <p dir="ltr" style={{ margin: "12px 0 0", paddingTop: 12, borderTop: "1px solid #c8f3e6", fontSize: 16, lineHeight: 1.7, color: "#3d4066", textAlign: "left" }}>{en}</p>}
        </div>
      </div>
    </section>
  );
}
