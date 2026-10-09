"use client";

import { useCallback, useSyncExternalStore } from "react";
import { useI18n } from "./I18nProvider";

type Theme = "dark" | "light";

const THEME_KEY = "finch-theme";

function readTheme(): Theme {
  if (typeof document === "undefined") return "dark";
  return document.documentElement.classList.contains("light") ? "light" : "dark";
}

// Berlangganan perubahan class <html>: sinkron dengan script anti-FOUC
// tanpa setState di dalam effect (react-hooks/set-state-in-effect).
function subscribeTheme(onChange: () => void): () => void {
  if (typeof document === "undefined") return () => {};
  const observer = new MutationObserver(onChange);
  observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
  return () => observer.disconnect();
}

function SunIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

function MoonIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export default function ThemeToggle() {
  const { dict } = useI18n();
  const theme = useSyncExternalStore(subscribeTheme, readTheme, () => "dark" as Theme);

  const toggle = useCallback(() => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.classList.toggle("light", next === "light");
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      // abaikan: tema sesi ini tetap berubah, hanya tidak tersimpan
    }
  }, [theme]);

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? dict.theme.toLight : dict.theme.toDark}
      title={theme === "dark" ? dict.theme.toLight : dict.theme.toDark}
      className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
    >
      {theme === "dark" ? <SunIcon /> : <MoonIcon />}
    </button>
  );
}
