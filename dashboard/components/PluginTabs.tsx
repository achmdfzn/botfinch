"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { PLUGIN_TABS, parsePluginTab, type PluginTab } from "@/lib/plugins";

export type { PluginTab };

function readTabFromUrl(): PluginTab {
  return parsePluginTab(new URLSearchParams(window.location.search).get("tab"));
}

function writeTabToUrl(tab: PluginTab) {
  const sp = new URLSearchParams(window.location.search);
  if (tab === "all") sp.delete("tab");
  else sp.set("tab", tab);
  const qs = sp.toString();
  window.history.replaceState(
    null,
    "",
    qs ? `${window.location.pathname}?${qs}` : window.location.pathname,
  );
}

/**
 * State tab kategori yang disinkron ke query URL (?tab=<grup>) via
 * history.replaceState: tautan bisa di-share dan link sidebar "?tab=..."
 * mendarat di tab yang benar — tanpa reload/refetch tiap ganti tab.
 */
export function usePluginTabQuery(initialTab: PluginTab): [PluginTab, (t: PluginTab) => void] {
  const [tab, setTab] = useState<PluginTab>(initialTab);

  // Navigasi client (mis. link sidebar ?tab=engagement) me-render ulang
  // halaman dengan initialTab baru: sesuaikan state saat render
  // (pola React "adjusting state during render", tanpa effect).
  const [prevInitial, setPrevInitial] = useState(initialTab);
  if (prevInitial !== initialTab) {
    setPrevInitial(initialTab);
    setTab(initialTab);
  }

  // Rapikan URL saat mount bila query tidak valid (mis. ?tab=asing).
  useEffect(() => {
    if (readTabFromUrl() !== tab) writeTabToUrl(tab);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Tulis tab ke URL setiap berubah (lewati render pertama).
  const firstChange = useRef(true);
  useEffect(() => {
    if (firstChange.current) {
      firstChange.current = false;
      return;
    }
    writeTabToUrl(tab);
  }, [tab]);

  // Tombol back/forward browser: tab mengikuti URL.
  useEffect(() => {
    const onPopState = () => setTab(readTabFromUrl());
    window.addEventListener("popstate", onPopState);
    return () => window.removeEventListener("popstate", onPopState);
  }, []);

  return [tab, setTab];
}

interface PluginTabsProps {
  tab: PluginTab;
  onChange: (t: PluginTab) => void;
  tabLabel: (t: PluginTab) => string;
  tablistLabel: string;
}

/**
 * Tab kategori ala WAI-ARIA (pola LeaderboardTabs): role=tablist/tab,
 * aria-selected + aria-controls ke panel, panah kiri/kanan pindah tab,
 * tab tak aktif tabIndex -1. Gaya underline ala referensi MEE6.
 */
export default function PluginTabs({ tab, onChange, tabLabel, tablistLabel }: PluginTabsProps) {
  const tabRefs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onTabKeyDown(e: KeyboardEvent, current: PluginTab) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = PLUGIN_TABS.indexOf(current);
    const next =
      PLUGIN_TABS[(i + (e.key === "ArrowRight" ? 1 : PLUGIN_TABS.length - 1)) % PLUGIN_TABS.length];
    onChange(next);
    tabRefs.current[next]?.focus();
  }

  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
      <div
        role="tablist"
        aria-label={tablistLabel}
        className="flex min-w-max gap-1 border-b border-edge sm:min-w-0 sm:flex-wrap"
      >
        {PLUGIN_TABS.map((t) => {
          const active = tab === t;
          return (
            <button
              key={t}
              ref={(el) => {
                tabRefs.current[t] = el;
              }}
              type="button"
              role="tab"
              id={`plugin-tab-${t}`}
              aria-selected={active}
              aria-controls="plugin-tabpanel"
              tabIndex={active ? 0 : -1}
              onClick={() => onChange(t)}
              onKeyDown={(e) => onTabKeyDown(e, t)}
              className={`-mb-px min-h-[44px] border-b-2 px-4 py-2.5 text-sm font-medium whitespace-nowrap transition-colors focus-visible:outline-2 focus-visible:outline-brand ${
                active
                  ? "border-brand text-fg"
                  : "border-transparent text-muted hover:border-edge hover:text-fg"
              }`}
            >
              {tabLabel(t)}
            </button>
          );
        })}
      </div>
    </div>
  );
}
