"use client";

import { useI18n } from "@/i18n/context";

export function LocaleSwitcher() {
  const { locale, setLocale } = useI18n();

  return (
    <div className="flex items-center bg-zinc-800 rounded-lg overflow-hidden text-xs">
      <button
        onClick={() => setLocale("en")}
        className={`px-2.5 py-1 transition-colors ${
          locale === "en" ? "bg-zinc-600 text-white" : "text-zinc-400 hover:text-white"
        }`}
      >
        EN
      </button>
      <button
        onClick={() => setLocale("zh")}
        className={`px-2.5 py-1 transition-colors ${
          locale === "zh" ? "bg-zinc-600 text-white" : "text-zinc-400 hover:text-white"
        }`}
      >
        中文
      </button>
    </div>
  );
}
