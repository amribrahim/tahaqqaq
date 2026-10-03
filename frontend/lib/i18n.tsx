"use client";

import { NextIntlClientProvider } from "next-intl";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import ar from "@/messages/ar.json";
import en from "@/messages/en.json";

export type Lang = "ar" | "en";
const MESSAGES = { ar, en } as const;
const KEY = "tahqaq.lang";

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "ar", setLang: () => {} });

export function LangProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>("ar");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(KEY);
      if (saved === "en" || saved === "ar") setLangState(saved);
    } catch {}
  }, []);

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "en" ? "ltr" : "rtl";
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setLangState(l);
    try { localStorage.setItem(KEY, l); } catch {}
  }, []);

  const value = useMemo(() => ({ lang, setLang }), [lang, setLang]);
  return (
    <LangCtx.Provider value={value}>
      <NextIntlClientProvider locale={lang} messages={MESSAGES[lang]} timeZone="Asia/Riyadh">
        {children}
      </NextIntlClientProvider>
    </LangCtx.Provider>
  );
}

export const useLang = () => useContext(LangCtx);
