"use client";

import { createContext, useContext, useState, useCallback, useEffect, type ReactNode } from "react";
import { locales, type Locale } from "./locales";

interface I18nContextValue {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: (key: string) => string;
}

const I18nContext = createContext<I18nContextValue>({
  locale: "en",
  setLocale: () => {},
  t: (key) => key,
});

export function I18nProvider({ children }: { children: ReactNode }) {
  // Always start with "en" to match server render, then sync on client
  const [locale, setLocaleState] = useState<Locale>("en");

  // After hydration, read saved preference or detect browser language
  useEffect(() => {
    const saved = localStorage.getItem("propguard-locale");
    if (saved === "zh" || saved === "en") {
      setLocaleState(saved);
    } else if (navigator.language.startsWith("zh")) {
      setLocaleState("zh");
    }
  }, []);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    localStorage.setItem("propguard-locale", l);
  }, []);

  const t = useCallback(
    (key: string) => locales[locale][key] || locales.en[key] || key,
    [locale]
  );

  return (
    <I18nContext.Provider value={{ locale, setLocale, t }}>
      {children}
    </I18nContext.Provider>
  );
}

export function useI18n() {
  return useContext(I18nContext);
}
