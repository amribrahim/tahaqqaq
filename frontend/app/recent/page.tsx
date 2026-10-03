"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo } from "react";
import { useLang } from "@/lib/i18n";
import { timeOf } from "@/lib/format";
import { clearHistory, HISTORY_KEY, type HistoryRow } from "@/lib/session";
import { notifyStorage, useStorageItem } from "@/lib/storage";
import { gradeFamily, GRADE_CHIP, STATE } from "@/lib/tokens";

export default function RecentPage() {
  const t = useTranslations("recent");
  const r = useTranslations("result");
  const s = useTranslations("states");
  const { lang } = useLang();
  const raw = useStorageItem("session", HISTORY_KEY, null);
  const rows = useMemo<HistoryRow[]>(() => { try { return raw ? JSON.parse(raw) : []; } catch { return []; } }, [raw]);
  const clear = () => { clearHistory(); notifyStorage(); };
  const via = (row: HistoryRow) => (row.via === "image" ? r("viaImage") : row.via === "url" ? r("viaUrl") : r("viaText")) + (row.lang === "en" ? ` · ${r("en")}` : "");
  const gradeColor = (g: string) => { const f = gradeFamily(g); return f === "other" ? "#3d4066" : GRADE_CHIP[f].fg; };
  const cols = "minmax(0,1fr) 250px 150px 110px 80px";
  return (
    <>
      <section className="hero">
        <div className="wrap" style={{ padding: "clamp(32px,4vw,56px) var(--gutter)", display: "flex", flexWrap: "wrap", alignItems: "flex-end", justifyContent: "space-between", gap: "16px 24px" }}>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <h1 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(30px,3.2vw,44px)", color: "#fff" }}>{t("title")}</h1>
            <p style={{ margin: 0, maxWidth: 560, fontSize: 16, lineHeight: 1.7, color: "#c9c3ff" }}>{t("sub")}</p>
          </div>
          {rows.length > 0 && <button data-testid="clear-history" onClick={clear} className="btn btn-m btn-dark-ghost" style={{ padding: "0 18px" }}>{t("clear")}</button>}
        </div>
      </section>
      <main id="main" className="wrap" style={{ padding: "32px var(--gutter) 72px", width: "100%" }}>
        {rows.length > 0 ? (
          <section className="card" style={{ padding: 0, overflow: "hidden" }}>
            <div className="hidden md:grid" style={{ gridTemplateColumns: cols, gap: 16, alignItems: "center", padding: "14px 24px", background: "#faf9fe", borderBottom: "1px solid #ebe9f5", fontSize: 13, fontWeight: 700, color: "#5a5d80" }}>
              <span>{t("text")}</span><span>{t("result")}</span><span>{t("grade")}</span><span>{t("time")}</span><span />
            </div>
            {rows.map((row) => {
              const st = STATE[row.state];
              const grade = row.grade + (row.closest && row.grade !== "—" ? ` ${t("closestGrade")}` : "");
              return (
                <div key={row.id} data-testid="history-row">
                  <div className="hidden md:grid hover:bg-[#fbfaff]" style={{ gridTemplateColumns: cols, gap: 16, alignItems: "center", padding: "16px 24px", borderBottom: "1px solid #f0eef8" }}>
                    <div style={{ display: "flex", flexDirection: "column", gap: 4, minWidth: 0 }}>
                      <span dir={row.lang === "en" ? "ltr" : "rtl"} style={{ fontSize: 16, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", textAlign: "start" }}>{row.text}</span>
                      <span style={{ fontSize: 12, color: "#5a5d80" }}>{via(row)}</span>
                    </div>
                    <span className="chip" style={{ justifySelf: "start", background: st.chipBg, color: st.chipFg }}><span className="dot" style={{ background: st.dot }} />{s(`${row.state}.label`, { grade: row.grade })}</span>
                    <span style={{ fontSize: 14, fontWeight: 700, color: gradeColor(row.grade) }}>{grade}</span>
                    <span style={{ fontSize: 14, color: "#5a5d80" }}>{timeOf(row.time, lang)}</span>
                    <Link href={`/result/?id=${row.id}`} className="btn btn-ghost" style={{ justifySelf: "end", height: 36, padding: "0 14px", borderRadius: 10, fontSize: 14, gap: 6 }}>{t("open")}<span>{lang === "ar" ? "←" : "→"}</span></Link>
                  </div>
                  <Link href={`/result/?id=${row.id}`} className="flex md:hidden" style={{ flexDirection: "column", gap: 10, padding: "16px 18px", borderBottom: "1px solid #f0eef8", color: "#14173d" }}>
                    <span dir={row.lang === "en" ? "ltr" : "rtl"} style={{ fontSize: 16, fontWeight: 500, lineHeight: 1.6, textAlign: "start" }}>{row.text}</span>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                      <span className="chip" style={{ padding: "4px 10px", fontSize: 12, background: st.chipBg, color: st.chipFg }}><span className="dot" style={{ width: 6, height: 6, background: st.dot }} />{s(`${row.state}.label`, { grade: row.grade })}</span>
                      <span style={{ fontSize: 13, fontWeight: 700, color: gradeColor(row.grade) }}>{grade}</span>
                    </div>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, color: "#5a5d80" }}><span>{via(row)} · {timeOf(row.time, lang)}</span><span style={{ color: "#4f3fd0", fontWeight: 700 }}>{t("open")} {lang === "ar" ? "←" : "→"}</span></div>
                  </Link>
                </div>
              );
            })}
          </section>
        ) : (
          <section className="card" data-testid="history-empty" style={{ boxShadow: "none", padding: "clamp(40px,6vw,72px) 24px", display: "flex", flexDirection: "column", alignItems: "center", gap: 14, textAlign: "center" }}>
            <span style={{ width: 64, height: 64, borderRadius: 20, background: "#f1effc", display: "grid", placeItems: "center" }}><span style={{ width: 22, height: 22, border: "2px solid #7c6cf0", borderRadius: 4, transform: "rotate(45deg)" }} /></span>
            <h2 className="font-cairo" style={{ margin: 0, fontWeight: 700, fontSize: 20 }}>{t("emptyTitle")}</h2>
            <p style={{ margin: 0, maxWidth: 380, fontSize: 15, lineHeight: 1.7, color: "#5a5d80" }}>{t("emptyHelp")}</p>
            <Link href="/" className="btn btn-primary" style={{ marginTop: 6, height: 48, padding: "0 24px", borderRadius: 14, fontSize: 16 }}>{t("start")}</Link>
          </section>
        )}
      </main>
    </>
  );
}
