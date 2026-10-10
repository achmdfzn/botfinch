"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useI18n } from "./I18nProvider";
import type { Lang } from "@/lib/i18n/client";

/**
 * Pemilih bahasa: tombol ikon globe + menu dropdown (ID/EN).
 *
 * A11y:
 * - Tombol: aria-haspopup="menu", aria-expanded, aria-label dari kamus
 *   (dict.lang.label). Target sentuh >=44px.
 * - Menu: role="menu", opsi role="menuitemradio" + aria-checked untuk bahasa
 *   aktif. Navigasi keyboard: Panah Bawah/Atas/Home/End antar opsi,
 *   Enter/Spasi memilih, Escape menutup + fokus kembali ke tombol,
 *   klik di luar menutup.
 * - Menu di-anchor ke kanan tombol (right-0) + max-w viewport agar tidak
 *   keluar layar di mobile.
 * - Ikon globe & centang: SVG inline ringan, aria-hidden (dekoratif).
 */
export default function LangSwitcher() {
  const { lang, setLang, dict } = useI18n();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  const options: { value: Lang; label: string; short: string }[] = [
    { value: "id", label: dict.lang.indonesian, short: "ID" },
    { value: "en", label: dict.lang.english, short: "EN" },
  ];
  const current = options.find((o) => o.value === lang) ?? options[0];

  const close = () => setOpen(false);
  const closeAndRefocus = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const choose = (value: Lang) => {
    if (value !== lang) setLang(value);
    closeAndRefocus();
  };

  // Klik di luar menutup menu.
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) close();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open ]);

  const focusItem = (index: number) => {
    const n = options.length;
    itemRefs.current[((index % n) + n) % n]?.focus();
  };

  const onTriggerKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setOpen(true);
      // Tunggu menu ter-render sebelum memindahkan fokus.
      requestAnimationFrame(() => focusItem(0));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setOpen(true);
      requestAnimationFrame(() => focusItem(options.length - 1));
    }
  };

  const onMenuKeyDown = (e: React.KeyboardEvent) => {
    const active = itemRefs.current.findIndex((el) => el === document.activeElement);
    if (e.key === "Escape") {
      e.preventDefault();
      closeAndRefocus();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      focusItem(active + 1);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      focusItem(active - 1);
    } else if (e.key === "Home") {
      e.preventDefault();
      focusItem(0);
    } else if (e.key === "End") {
      e.preventDefault();
      focusItem(options.length - 1);
    } else if (e.key === "Tab") {
      close();
    }
  };

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={dict.lang.label}
        title={dict.lang.label}
        className="flex min-h-[44px] min-w-[44px] items-center justify-center gap-1.5 rounded-lg border border-edge px-2.5 text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
      >
        <svg
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
          strokeLinecap="round"
          aria-hidden="true"
        >
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h18" />
          <path d="M12 3c2.5 2.6 3.9 5.7 3.9 9S14.5 18.4 12 21c-2.5-2.6-3.9-5.7-3.9-9S9.5 5.6 12 3Z" />
        </svg>
        <span className="text-xs font-bold tracking-wide">{current.short}</span>
        <svg
          width="12"
          height="12"
          viewBox="0 0 12 12"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden="true"
          className={`text-muted transition-transform motion-reduce:transition-none ${open ? "rotate-180" : ""}`}
        >
          <path d="M2.5 4.5 6 8l3.5-3.5" />
        </svg>
      </button>

      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={dict.lang.label}
          onKeyDown={onMenuKeyDown}
          className="absolute right-0 top-full z-50 mt-2 w-52 max-w-[calc(100vw-2rem)] rounded-xl border border-edge bg-panel p-1.5 shadow-xl"
        >
          {options.map((o, i) => {
            const active = o.value === lang;
            return (
              <button
                key={o.value}
                ref={(el) => {
                  itemRefs.current[i] = el;
                }}
                type="button"
                role="menuitemradio"
                aria-checked={active}
                onClick={() => choose(o.value)}
                className={`flex min-h-[44px] w-full items-center gap-2.5 rounded-lg px-3 text-left text-sm focus-visible:outline-2 focus-visible:outline-brand ${
                  active ? "bg-edge font-semibold text-fg" : "text-muted hover:bg-edge hover:text-fg"
                }`}
              >
                <span
                  aria-hidden="true"
                  className="flex w-4 shrink-0 items-center justify-center text-fg"
                >
                  {active && (
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 14 14"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2.2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M2.5 7.5 6 11l5.5-7" />
                    </svg>
                  )}
                </span>
                {o.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
