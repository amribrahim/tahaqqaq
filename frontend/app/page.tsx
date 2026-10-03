"use client";

import { useTranslations } from "next-intl";
import { useState } from "react";
import { VerifyCard } from "@/components/home/VerifyCard";
import { ExampleChips } from "@/components/home/ExampleChips";

export default function Home() {
  const t = useTranslations("home");
  const [text, setText] = useState("");
  const [tab, setTab] = useState<"text" | "image" | "url">("text");
  return (
    <>
      <section className="hero" style={{ paddingBottom: 150 }}>
        <div style={{ maxWidth: 860, margin: "0 auto", padding: "clamp(48px,7vw,96px) clamp(16px,4vw,32px) 0", display: "flex", flexDirection: "column", alignItems: "center", gap: 18, textAlign: "center" }}>
          <h1 className="font-cairo" style={{ margin: 0, fontWeight: 800, fontSize: "clamp(38px,4.4vw,64px)", lineHeight: 1.25, color: "#fff", textWrap: "balance" }}>
            {t("title1")}<span style={{ color: "#3ee6c0" }}>{t("title2")}</span>
          </h1>
          <p style={{ margin: 0, maxWidth: 620, fontSize: "clamp(16px,1.5vw,20px)", lineHeight: 1.8, color: "#c9c3ff", textWrap: "pretty" }}>{t("sub")}</p>
        </div>
      </section>
      <main id="main" style={{ padding: "0 clamp(16px,4vw,32px) 72px" }}>
        <div style={{ maxWidth: 860, margin: "-110px auto 0", display: "flex", flexDirection: "column", gap: 28 }}>
          <VerifyCard text={text} setText={setText} tab={tab} setTab={setTab} />
          <ExampleChips onPick={(x) => { setText(x); setTab("text"); }} />
        </div>
      </main>
    </>
  );
}
