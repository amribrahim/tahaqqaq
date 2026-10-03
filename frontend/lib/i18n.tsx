"use client";

import { NextIntlClientProvider } from "next-intl";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { notifyStorage, useStorageItem } from "@/lib/storage";
import ar from "@/messages/ar.json";
import en from "@/messages/en.json";

export type Lang = "ar" | "en";
const MESSAGES = { ar, en } as const;
const KEY = "tahqaq.lang";

const LangCtx = createContext<{ lang: Lang; setLang: (l: Lang) => void }>({ lang: "ar", setLang: () => {} });

export function LangProvider({ children }: { children: React.ReactNode }) {
  const saved = useStorageItem("local", KEY, "ar");
  const [chosen, setChosen] = useState<Lang | null>(null);   // used when storage is unavailable
  const lang: Lang = chosen ?? (saved === "en" ? "en" : "ar");

  useEffect(() => {
    document.documentElement.lang = lang;
    document.documentElement.dir = lang === "en" ? "ltr" : "rtl";
  }, [lang]);

  const setLang = useCallback((l: Lang) => {
    setChosen(l);
    try { localStorage.setItem(KEY, l); } catch {}
    notifyStorage();
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
