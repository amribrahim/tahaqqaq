"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";

export function ErrorCard({ code, message, onRetry }: { code: string; message?: string; onRetry: () => void }) {
  const t = useTranslations("result");
  const title = code === "ocr_failed" ? t("errOcr") : code === "url_unreachable" ? t("errUrl") : code === "too_long" ? t("errLong") : t("errTitle");
  return (
    <section className="card" data-testid="error-card" data-code={code} style={{ border: "1px solid #f6dde2", display: "flex", flexDirection: "column", gap: 18 }}>
      <div style={{ display: "flex", gap: 14, alignItems: "flex-start" }}>
        <span className="font-cairo" style={{ flex: "none", width: 40, height: 40, borderRadius: 12, background: "#fde4e8", color: "#a8324a", display: "grid", placeItems: "center", fontWeight: 800, fontSize: 20 }}>!</span>
        <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
          <h3 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: 20 }}>{title}</h3>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.7, color: "#3d4066" }}>{code === "url_unreachable" ? t("errUrlBody") : t("errBody")}</p>
          {message && <p dir="ltr" style={{ margin: 0, fontSize: 12, color: "#8e90ad", fontFamily: "ui-monospace, Menlo, monospace", textAlign: "start" }}>{message}</p>}
        </div>
      </div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>
        <button onClick={onRetry} className="btn btn-l btn-primary">{t("retry")}</button>
        <Link href="/" className="btn btn-l btn-ghost">{t("edit")}</Link>
      </div>
    </section>
  );
}
