"use client";

import { useRef, useState, type ReactNode } from "react";
import { useI18n } from "./I18nProvider";

/**
 * Tab Ringkasan/Pengaturan di halaman overview server.
 * Dua panel di-render server; tab hanya mengatur visibilitas (tanpa fetch ulang).
 */
export default function GuildTabs({
  overview,
  settings,
}: {
  overview: ReactNode;
  settings: ReactNode;
}) {
  const { dict } = useI18n();
  const t = dict.guild.overview;
  const tabs = [
    { key: "overview", label: t.tabOverview },
    { key: "settings", label: t.tabSettings },
  ] as const;
  const [active, setActive] = useState<(typeof tabs)[number]["key"]>("overview");
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = e.key === "ArrowRight" ? (i + 1) % tabs.length : (i - 1 + tabs.length) % tabs.length;
    setActive(tabs[next].key);
    tabRefs.current[next]?.focus();
  }

  return (
    <div>
      <div className="flex gap-1 border-b border-edge" role="tablist" aria-label={t.tablistLabel}>
        {tabs.map((tt, i) => (
          <button
            key={tt.key}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            role="tab"
            id={`tab-${tt.key}`}
            aria-selected={active === tt.key}
            aria-controls={`panel-${tt.key}`}
            tabIndex={active === tt.key ? 0 : -1}
            onClick={() => setActive(tt.key)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`rounded-t-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand min-h-[44px] ${
              active === tt.key
                ? "border-b-2 border-brand bg-panel text-fg"
                : "text-muted hover:text-fg"
            }`}
          >
            {tt.label}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id="panel-overview"
        aria-labelledby="tab-overview"
        hidden={active !== "overview"}
        className="pt-6"
      >
        {overview}
      </div>
      <div
        role="tabpanel"
        id="panel-settings"
        aria-labelledby="tab-settings"
        hidden={active !== "settings"}
        className="pt-6"
      >
        {settings}
      </div>
    </div>
  );
}
