"use client";

import { useTranslations } from "next-intl";

const EXAMPLES = [
  { key: "ex1", text: "إنما الأعمال بالنيات، وإنما لكل امرئ ما نوى", bg: "#dcfaf1", fg: "#087a62", ltr: false },
  { key: "ex2", text: "من عرف نفسه فقد عرف ربه", bg: "#fde4e8", fg: "#a8324a", ltr: false },
  { key: "ex3", text: "None of you is a Muslim until he loves for his brother what he loves for himself.", bg: "#fdf0d9", fg: "#8a5300", ltr: true },
];

export function ExampleChips({ onPick }: { onPick: (text: string) => void }) {
  const t = useTranslations("home");
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
      <span style={{ fontSize: 14, fontWeight: 700, color: "#5a5d80" }}>{t("tryExample")}</span>
      <div className="flex flex-wrap sm:flex-nowrap" style={{ gap: 10 }}>
        {EXAMPLES.map((ex) => (
          <button key={ex.key} data-testid={`example-${ex.key}`} onClick={() => onPick(ex.text)} className="hover:!border-[#7c6cf0]"
            style={{ display: "flex", alignItems: "center", gap: 10, minHeight: 44, minWidth: 0, padding: "6px 8px", paddingInlineEnd: 16, borderRadius: 999, border: "1px solid #e3e0f2", background: "#fff", cursor: "pointer", fontFamily: "var(--font-tajawal)", fontSize: 15, color: "#14173d" }}>
            <span style={{ flex: "none", padding: "4px 10px", borderRadius: 999, background: ex.bg, color: ex.fg, fontSize: 12, fontWeight: 700, whiteSpace: "nowrap" }}>{t(`${ex.key}g`)}</span>
            <span dir={ex.ltr ? "ltr" : "rtl"} style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{t(ex.key)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}
