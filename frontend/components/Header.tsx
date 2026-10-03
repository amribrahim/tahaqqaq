"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { useLang } from "@/lib/i18n";
import { LogoMark } from "./Logo";

export function Header() {
  const t = useTranslations("nav");
  const b = useTranslations("brand");
  const { lang, setLang } = useLang();
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const items = [
    { key: "home", href: "/", label: t("home") },
    { key: "sources", href: "/sources/", label: t("sources") },
    { key: "recent", href: "/recent/", label: t("recent") },
  ];
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/result") : path.startsWith(href.replace(/\/$/, "")));
  const pill = (on: boolean) => ({ background: on ? "#fff" : "transparent", color: on ? "#0d1035" : "#c9c3ff" });

  return (
    <header className="container-x" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 24, height: 72, borderBottom: "1px solid rgba(201,195,255,0.12)" }}>
      <Link href="/" style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <LogoMark />
        <span style={{ display: "flex", flexDirection: "column", lineHeight: 1 }}>
          <span className="font-cairo" style={{ fontWeight: 800, fontSize: 22, color: "#fff" }}>{b("name")}</span>
          <span style={{ fontSize: 10, letterSpacing: "0.2em", color: "#c9c3ff", textTransform: "uppercase", marginTop: 4 }}>{b("latin")}</span>
        </span>
      </Link>
      <nav className="hidden sm:flex" style={{ gap: 4 }}>
        {items.map((it) => (
          <Link key={it.key} href={it.href} className="hover:!text-white"
            style={{ padding: "8px 16px", borderRadius: 10, fontSize: 15, fontWeight: 500, color: active(it.href) ? "#fff" : "#c9c3ff", background: active(it.href) ? "rgba(124,108,240,0.24)" : "transparent" }}>
            {it.label}
          </Link>
        ))}
      </nav>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <div role="group" aria-label="Language" style={{ display: "flex", gap: 2, padding: 3, borderRadius: 999, border: "1px solid rgba(201,195,255,0.3)" }}>
          <button data-testid="lang-ar" aria-label="العربية" aria-pressed={lang === "ar"} onClick={() => setLang("ar")} className="font-cairo" style={{ border: 0, cursor: "pointer", height: 34, minWidth: 42, padding: "0 12px", borderRadius: 999, fontWeight: 700, fontSize: 15, ...pill(lang === "ar") }}>ع</button>
          <button data-testid="lang-en" aria-label="English" aria-pressed={lang === "en"} onClick={() => setLang("en")} className="font-cairo" style={{ border: 0, cursor: "pointer", height: 34, minWidth: 42, padding: "0 12px", borderRadius: 999, fontWeight: 700, fontSize: 13, letterSpacing: "0.04em", ...pill(lang === "en") }}>EN</button>
        </div>
        <button aria-label={t("menu")} onClick={() => setOpen(!open)} className="flex sm:hidden" style={{ width: 44, height: 44, borderRadius: 12, border: "1px solid rgba(201,195,255,0.3)", background: "transparent", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 5, cursor: "pointer" }}>
          {[0, 1, 2].map((i) => <span key={i} style={{ width: 18, height: 2, borderRadius: 2, background: "#fff" }} />)}
        </button>
      </div>
      {open && (
        <nav className="flex sm:hidden" style={{ position: "absolute", top: 72, insetInlineEnd: 16, background: "#0d1035", border: "1px solid rgba(201,195,255,0.2)", borderRadius: 14, padding: 8, flexDirection: "column", zIndex: 20 }}>
          {items.map((it) => <Link key={it.key} href={it.href} onClick={() => setOpen(false)} style={{ padding: "10px 16px", color: "#fff", fontSize: 15 }}>{it.label}</Link>)}
        </nav>
      )}
    </header>
  );
}
