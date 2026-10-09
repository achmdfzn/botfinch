"use client";

import { useRef, useState, type ReactNode } from "react";
import { useI18n } from "./I18nProvider";

interface TabDef {
  key: string;
  label: string;
  panel: ReactNode;
}

/**
 * Tab di halaman overview server.
 * Semua panel di-render server; tab hanya mengatur visibilitas (tanpa fetch ulang).
 * Bila prop `plugins` diberikan, tab Plugins jadi default aktif dan urutan
 * tab menjadi Plugins > Ringkasan > Pengaturan. Tanpa prop itu, perilaku lama
 * (Ringkasan > Pengaturan) tetap jalan.
 */
export default function GuildTabs({
  overview,
  settings,
  plugins,
}: {
  overview: ReactNode;
  settings: ReactNode;
  /** Panel browser plugin ala MEE6; opsional agar pemakaian lama 2 tab tidak rusak. */
  plugins?: ReactNode;
}) {
  const { dict } = useI18n();
  const t = dict.guild.overview;
  const tabs: TabDef[] =
    plugins !== undefined
      ? [
          { key: "plugins", label: t.tabPlugins, panel: plugins },
          { key: "overview", label: t.tabOverview, panel: overview },
          { key: "settings", label: t.tabSettings, panel: settings },
        ]
      : [
          { key: "overview", label: t.tabOverview, panel: overview },
          { key: "settings", label: t.tabSettings, panel: settings },
        ];
  const [active, setActive] = useState(tabs[0].key);
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

      {tabs.map((tt) => (
        <div
          key={tt.key}
          role="tabpanel"
          id={`panel-${tt.key}`}
          aria-labelledby={`tab-${tt.key}`}
          hidden={active !== tt.key}
          className="pt-6"
        >
          {tt.panel}
        </div>
      ))}
    </div>
  );
}
