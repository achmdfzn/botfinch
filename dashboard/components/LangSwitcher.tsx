"use client";

import { useI18n } from "./I18nProvider";
import type { Lang } from "@/lib/i18n/client";

const OPTIONS: { value: Lang; short: string }[] = [
  { value: "id", short: "ID" },
  { value: "en", short: "EN" },
];

export default function LangSwitcher() {
  const { lang, setLang, dict } = useI18n();

  return (
    <div
      role="group"
      aria-label={dict.lang.label}
      className="flex shrink-0 items-center rounded-lg border border-edge p-0.5"
    >
      {OPTIONS.map((o) => {
        const label = o.value === "id" ? dict.lang.indonesian : dict.lang.english;
        const active = lang === o.value;
        return (
          <button
            key={o.value}
            type="button"
            onClick={() => setLang(o.value)}
            aria-pressed={active}
            aria-label={label}
            title={label}
            className={`flex min-h-[44px] min-w-[44px] items-center justify-center rounded-md px-2 text-xs font-bold tracking-wide focus-visible:outline-2 focus-visible:outline-brand ${
              active ? "bg-brand text-ink" : "text-muted hover:bg-edge hover:text-fg"
            }`}
          >
            {o.short}
          </button>
        );
      })}
    </div>
  );
}
