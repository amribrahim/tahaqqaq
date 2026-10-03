"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { notifyStorage, useStorageItem } from "@/lib/storage";

const KEY = "tahqaq.banner.dismissed";

/** First-visit notice: AI-assisted tool, no verdicts, no server-side storage. Dismissible. */
export function AiBanner() {
  const t = useTranslations("banner");
  const dismissed = useStorageItem("local", KEY, "1");   // hidden in the static HTML, shown after hydration if not dismissed
  const [closed, setClosed] = useState(false);
  if (dismissed === "1" || closed) return null;
  const dismiss = () => { try { localStorage.setItem(KEY, "1"); } catch {} setClosed(true); notifyStorage(); };
  return (
    <div role="status" data-testid="ai-banner" className="no-print" style={{ background: "#ecebfe", color: "#4f3fd0", borderBottom: "1px solid #d9d5f5" }}>
      <div className="wrap container-x" style={{ display: "flex", alignItems: "center", gap: 16, padding: "10px var(--gutter)", fontSize: 14, lineHeight: 1.6 }}>
        <span aria-hidden style={{ flex: "none", width: 8, height: 8, background: "#7c6cf0", transform: "rotate(45deg)" }} />
        <span style={{ flex: 1 }}>{t("text")}</span>
        <button data-testid="ai-banner-dismiss" onClick={dismiss} className="btn btn-s btn-secondary" style={{ flex: "none" }}>{t("dismiss")}</button>
      </div>
    </div>
  );
}
