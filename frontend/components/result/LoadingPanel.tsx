"use client";

import { useTranslations } from "next-intl";
import { useLang } from "@/lib/i18n";
import { num } from "@/lib/format";

export function LoadingPanel({ step }: { step: number }) {
  const t = useTranslations("result");
  const { lang } = useLang();
  const steps = t.raw("steps") as string[];
  const desc = t.raw("stepDesc") as string[];
  return (
    <div data-testid="loading-panel" role="status" aria-live="polite" aria-busy="true" style={{ padding: "clamp(20px,2.4vw,32px)", borderRadius: 20, background: "rgba(255,255,255,0.04)", border: "1px solid rgba(201,195,255,0.2)", display: "flex", flexDirection: "column", gap: 28 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span className="spinner" aria-hidden="true" />
        <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
          <h2 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(22px,2.6vw,30px)", color: "#fff" }}>{t("loadingTitle")}</h2>
          <p style={{ margin: 0, fontSize: 15, lineHeight: 1.6, color: "#c9c3ff" }}>{t("loadingSub")}</p>
        </div>
      </div>
      <ol style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gridTemplateColumns: "repeat(4, minmax(0,1fr))", gap: "clamp(6px,1vw,12px)" }}>
        {steps.map((label, i) => {
          const done = i < step, now = i === step;
          return (
            <li key={label} data-testid="loading-step" style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 0 }}>
              <div style={{ height: 4, borderRadius: 99, background: done ? "#3ee6c0" : now ? "#7c6cf0" : "rgba(255,255,255,0.12)" }} />
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span style={{ width: 26, height: 26, borderRadius: "50%", display: "grid", placeItems: "center", fontSize: 13, fontWeight: 700, background: done ? "#3ee6c0" : "transparent", color: done ? "#0d1035" : now ? "#fff" : "#c9c3ff", border: `1.5px solid ${done ? "#3ee6c0" : now ? "#7c6cf0" : "rgba(201,195,255,0.35)"}` }}>
                  {done ? "✓" : num(i + 1, lang)}
                </span>
                <span className="font-cairo" style={{ fontWeight: 700, fontSize: 15, color: done || now ? "#fff" : "#c9c3ff" }}>{label}</span>
              </div>
              <span style={{ fontSize: 13, lineHeight: 1.5, color: "#c9c3ff" }}>{desc[i]}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export function SkeletonCards({ inputText, inputLabel }: { inputText: string; inputLabel: string }) {
  return (
    <>
      <section className="card" style={{ display: "flex", flexDirection: "column", gap: 12 }}>
        <span className="label">{inputLabel}</span>
        <p dir="auto" style={{ margin: 0, fontSize: 22, lineHeight: 2, fontWeight: 500 }}>{inputText}</p>
      </section>
      <section className="card" style={{ boxShadow: "none", display: "flex", flexDirection: "column", gap: 14 }}>
        <div className="skeleton-bar" style={{ width: "38%", height: 16 }} />
        <div className="skeleton-line" style={{ width: "100%", height: 12 }} />
        <div className="skeleton-line" style={{ width: "86%", height: 12 }} />
        <div className="skeleton-line" style={{ width: "64%", height: 12 }} />
      </section>
    </>
  );
}
