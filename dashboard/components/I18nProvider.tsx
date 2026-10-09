"use client";

import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getDict, type Dict, type Lang } from "@/lib/i18n/client";

interface I18nContextValue {
  lang: Lang;
  dict: Dict;
  setLang: (lang: Lang) => void;
}

const I18nContext = createContext<I18nContextValue | null>(null);

export function useI18n(): I18nContextValue {
  const ctx = useContext(I18nContext);
  if (!ctx) throw new Error("useI18n harus dipakai di dalam <I18nProvider>");
  return ctx;
}

const LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365; // 1 tahun

export default function I18nProvider({
  lang: initialLang,
  dict: initialDict,
  children,
}: {
  lang: Lang;
  dict: Dict;
  children: ReactNode;
}) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  const [dict, setDictState] = useState<Dict>(initialDict);
  const router = useRouter();

  const setLang = useCallback(
    (next: Lang) => {
      setLangState(next);
      setDictState(getDict(next));
      try {
        localStorage.setItem("finch-lang", next);
      } catch {
        // penyimpanan lokal tidak tersedia: cookie tetap jadi sumber kebenaran
      }
      document.cookie = `finch-lang=${next}; path=/; max-age=${LANG_COOKIE_MAX_AGE}; samesite=lax`;
      document.documentElement.lang = next;
      router.refresh(); // render ulang Server Component dengan kamus baru
    },
    [router],
  );

  return <I18nContext.Provider value={{ lang, dict, setLang }}>{children}</I18nContext.Provider>;
}
