"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function Footer() {
  const t = useTranslations("footer");
  const b = useTranslations("brand");
  const link = { fontSize: 15, fontWeight: 500, color: "#fff" } as const;
  return (
    <footer className="no-print" style={{ background: "#0d1035", borderTop: "1px solid rgba(201,195,255,0.12)", marginTop: "auto" }}>
      <div className="wrap container-x" style={{ padding: "32px var(--gutter)", display: "flex", flexWrap: "wrap", gap: "20px 40px", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <span className="font-cairo" style={{ fontWeight: 800, fontSize: 20, color: "#fff" }}>{b("name")}</span>
          <span style={{ fontSize: 14, color: "#c9c3ff" }}>{b("challenge")}</span>
        </div>
        <nav style={{ display: "flex", flexWrap: "wrap", gap: "8px 28px" }}>
          <Link href="/sources/" className="hover:!text-[#3ee6c0]" style={link}>{t("sources")}</Link>
          <Link href="/sources/#method" className="hover:!text-[#3ee6c0]" style={link}>{t("method")}</Link>
          <a href="https://github.com/" target="_blank" rel="noreferrer" className="hover:!text-[#3ee6c0]" style={link}>{t("challenge")}</a>
        </nav>
      </div>
      <div className="wrap" style={{ padding: "14px var(--gutter) 20px", borderTop: "1px solid rgba(201,195,255,0.08)", fontSize: 12, lineHeight: 1.6, color: "#9d97d6", display: "flex", flexDirection: "column", gap: 4 }}>
        <span data-testid="ai-notice" style={{ color: "#c9c3ff" }}>🤖 {t("ai")}</span>
        <span>{t("demo")}</span>
      </div>
    </footer>
  );
}
