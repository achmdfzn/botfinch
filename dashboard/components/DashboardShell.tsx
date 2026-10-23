"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import Sidebar, { type SidebarNavItem } from "@/components/Sidebar";
import { useI18n } from "@/components/I18nProvider";
import { buildSidebarGroups } from "@/lib/sidebar-nav";
import LangSwitcher from "@/components/LangSwitcher";

interface Props {
  guildName: string;
  guildIconUrl: string | null;
  navItems: SidebarNavItem[];
  children: ReactNode;
}

const SIDEBAR_COLLAPSED_KEY = "finch-sidebar-collapsed";
const SIDEBAR_COLLAPSED_EVENT = "finch-sidebar-collapsed-change";

/** Store eksternal untuk preferensi collapse di localStorage. */
function subscribeCollapsed(onChange: () => void) {
  window.addEventListener("storage", onChange);
  window.addEventListener(SIDEBAR_COLLAPSED_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", onChange);
    window.removeEventListener(SIDEBAR_COLLAPSED_EVENT, onChange);
  };
}

function getCollapsedSnapshot(): string {
  try {
    return window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) ?? "0";
  } catch {
    return "0";
  }
}

function getCollapsedServerSnapshot(): string {
  return "0";
}

/**
 * Kerangka halaman per-server: topbar mobile (hamburger 44px + nama server),
 * sidebar sticky di desktop (>=lg), drawer geser di mobile (<lg).
 *
 * Sidebar dirangkai dari navItems layout (href kanonis) + kamus lewat
 * buildSidebarGroups (lib/sidebar-nav): grup Ringkasan, Modul & Fitur
 * (halaman Modul + seksi plugin tersaring), Konten & Komunitas,
 * Pengaturan, Billing VIP — setiap route per-guild tepat satu kali.
 *
 * Collapse desktop: state "finch-sidebar-collapsed" di localStorage,
 * hanya berlaku >=lg (aside disembunyikan di bawah lg; drawer mobile
 * selalu dirender melebar dan tidak membaca state ini).
 */
export default function DashboardShell({ guildName, guildIconUrl, navItems, children }: Props) {
  const { dict } = useI18n();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  // Preferensi collapse dibaca lewat useSyncExternalStore: snapshot
  // server selalu "0" (melebar) sehingga HTML SSR dan render hidrasi
  // pertama sama, lalu nilai localStorage diterapkan React tanpa
  // setState di dalam effect (dan tanpa hydration mismatch).
  const collapsed =
    useSyncExternalStore(
      subscribeCollapsed,
      getCollapsedSnapshot,
      getCollapsedServerSnapshot,
    ) === "1";
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  const toggleCollapsed = useCallback(() => {
    try {
      window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed ? "0" : "1");
    } catch {
      // abaikan: penyimpanan gagal, state tidak berubah
    }
    // Event "storage" tidak terpicu di tab yang sama; beri tahu store
    // secara manual agar snapshot dibaca ulang.
    window.dispatchEvent(new Event(SIDEBAR_COLLAPSED_EVENT));
  }, [collapsed]);

  // Tutup manual (Escape / overlay / tombol X): fokus kembali ke hamburger.
  const close = useCallback(() => {
    setOpen(false);
    menuButtonRef.current?.focus();
  }, []);

  // Tutup tanpa memindahkan fokus: dipakai saat navigasi dari dalam drawer
  // (klik link) — pengguna sudah berpindah halaman, fokus jangan ditarik
  // kembali ke tombol hamburger.
  const closeSilently = useCallback(() => {
    setOpen(false);
  }, []);

  // Drawer tertutup otomatis saat route berubah (klik link di dalam drawer
  // memicu onNavigate lebih dulu, ini jaring pengaman untuk navigasi lain,
  // mis. tombol back browser) — tanpa mengembalikan fokus. Pola "sesuaikan
  // state selama render" dari dokumentasi React, bukan effect.
  const [prevPathname, setPrevPathname] = useState(pathname);
  if (pathname !== prevPathname) {
    setPrevPathname(pathname);
    setOpen(false);
  }

  // Drawer: Escape menutup; kunci scroll body saat terbuka.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, close]);

  // Saat drawer dibuka, pindahkan fokus ke elemen pertama di dalam panel;
  // trap Tab di dalam drawer sampai ditutup.
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusables = () =>
      [...panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )].filter((el) => el.offsetParent !== null);
    focusables()[0]?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const els = focusables();
      if (els.length === 0) return;
      const firstEl = els[0];
      const lastEl = els[els.length - 1];
      if (e.shiftKey && document.activeElement === firstEl) {
        e.preventDefault();
        lastEl.focus();
      } else if (!e.shiftKey && document.activeElement === lastEl) {
        e.preventDefault();
        firstEl.focus();
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const sub = dict.guild.subnav;
  const pl = dict.guild.plugins;
  const cards = pl.cards as Record<string, { name: string; desc: string }>;

  // navItems[0] adalah home per-server ("/dashboard/<guildId>") dari layout;
  // semua route lain = home + rel. Fallback merakit href dari rel bila
  // layout berubah, agar tidak ada route yang mati.
  const homeHref = navItems[0]?.href ?? "/dashboard";
  const hrefFor = (rel: string): string => {
    const found = navItems.find((i) => i.href === `${homeHref}${rel}`);
    return found ? found.href : `${homeHref}${rel}`;
  };

  const groups = buildSidebarGroups({
    homeHref,
    hrefFor,
    labels: {
      groupTitles: sub.groups,
      pluginGroupTitles: {
        essentials: pl.groupEssentials,
        engagement: pl.groupEngagement,
        moderation: pl.groupModeration,
        utilities: pl.groupUtilities,
      },
      plugins: sub.plugins,
      overview: sub.overview,
      leaderboard: sub.leaderboard,
      template: dict.templates.navLabel,
      embed: sub.embed,
      selfroles: sub.selfroles,
      responder: sub.responder,
      giveaway: sub.giveaway,
      pengumuman: sub.pengumuman,
      settings: sub.settings,
      modlog: sub.modlog,
      modul: sub.modul,
      billing: dict.billing.title,
      pluginNames: Object.fromEntries(Object.entries(cards).map(([id, c]) => [id, c.name])),
    },
  });

  const sidebarProps = {
    guildName,
    guildIconUrl,
    groups,
    backHref: "/dashboard",
    backLabel: dict.nav.back,
    sectionLabel: sub.sectionLabel,
    serverMenuLabel: sub.serverMenuLabel,
    expandSectionLabel: sub.expandSection,
    collapseSectionLabel: sub.collapseSection,
  };

  return (
    <div className="min-h-screen bg-ink">
      <a
        href="#konten-utama"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-brand focus:px-4 focus:py-2 focus:font-semibold focus:text-ink"
      >
        {dict.dashboard.skipToContent}
      </a>
      {/* Topbar mobile: hanya tampil di bawah lg */}
      <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-edge bg-ink px-3 lg:hidden">
        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={open ? sub.closeMenu : sub.openMenu}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-edge text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
        >
          <svg
            width="20"
            height="20"
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            aria-hidden="true"
          >
            {open ? <path d="M4 4l12 12M16 4L4 16" /> : <path d="M3 5h14M3 10h14M3 15h14" />}
          </svg>
        </button>
        <span className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">{guildName}</span>
        {/* Ganti bahasa tanpa membuka drawer. */}
        <LangSwitcher />
      </div>

      {/* Full-width: sidebar menempel tepi kiri viewport, konten memakai
          seluruh sisa lebar (min-w-0 flex-1, tanpa max-w terpusat). */}
      <div className="flex w-full">
        {/* Sidebar desktop: kolom kiri sticky, hanya >=lg. Lebar mengikuti
            state collapse (w-64 melebar / w-24 ikon saja). */}
        <aside className={`hidden shrink-0 lg:block ${collapsed ? "w-24" : "w-64"}`}>
          <div className="sticky top-0 h-screen border-r border-edge bg-panel">
            <Sidebar
              {...sidebarProps}
              collapsed={collapsed}
              collapseToggle={{
                collapsed,
                onToggle: toggleCollapsed,
                collapseLabel: sub.collapseSidebar,
                expandLabel: sub.expandSidebar,
              }}
            />
          </div>
        </aside>

        {/* Skip link: fokus ikut pindah ke main (tabIndex -1). */}
        <main id="konten-utama" tabIndex={-1} className="min-w-0 flex-1">
          <div className="w-full px-4 py-5 sm:px-6 lg:px-8 lg:py-7">{children}</div>
        </main>
      </div>

      {/* Drawer mobile (<lg) */}
      {open && (
        <div
          className="fixed inset-0 z-40 lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label={sub.sectionLabel}
        >
          {/* Overlay: klik menutup drawer (fokus kembali ke hamburger). */}
          <button
            type="button"
            aria-label={sub.closeMenu}
            onClick={close}
            className="absolute inset-0 h-full w-full cursor-default bg-ink/70 focus-visible:outline-2 focus-visible:outline-brand"
          />
          <div
            ref={panelRef}
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-edge bg-panel"
          >
            {/* Header drawer: nama server + tombol X eksplisit (44px,
                label dict.guild.subnav.closeMenu). */}
            <div className="flex items-center justify-between gap-2 border-b border-edge px-3 py-2">
              <span className="min-w-0 flex-1 truncate text-sm font-semibold text-fg">{guildName}</span>
              <button
                type="button"
                onClick={close}
                aria-label={sub.closeMenu}
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-edge text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
              >
                <svg
                  width="20"
                  height="20"
                  viewBox="0 0 20 20"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  aria-hidden="true"
                >
                  <path d="M4 4l12 12M16 4L4 16" />
                </svg>
              </button>
            </div>
            <Sidebar {...sidebarProps} onNavigate={closeSilently} />
          </div>
        </div>
      )}
    </div>
  );
}
