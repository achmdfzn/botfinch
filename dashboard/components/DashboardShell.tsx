"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import Sidebar, {
  type SidebarNavItem,
  type SidebarEntry,
  type SidebarSection,
  type SidebarIconId,
} from "@/components/Sidebar";
import { useI18n } from "@/components/I18nProvider";
import { PLUGINS, type PluginGroup } from "@/lib/plugins";

interface Props {
  guildName: string;
  guildIconUrl: string | null;
  navItems: SidebarNavItem[];
  children: ReactNode;
}

/**
 * Kerangka halaman per-server: topbar mobile (hamburger 44px + nama server),
 * sidebar sticky di desktop, drawer geser di mobile. Bersifat aditif: halaman
 * di dalamnya tetap me-render kontennya sendiri.
 *
 * Sidebar dibangun di sini dari navItems (untuk href) + dict
 * (untuk label): item utama (Plugins, Ringkasan, Leaderboard, Templates,
 * Pengaturan), seksi plugin berkelompok (Esensial, Engagement & Fun,
 * Moderasi, Utilitas), lalu divider + item bawah (Mod Log, Modul).
 *
 * Tujuan link per plugin:
 * - punya halaman konfigurasi (selfroles, responder, giveaway, pengumuman,
 *   embed, template) -> halaman konfigurasinya langsung;
 * - welcome -> seksi welcome di /settings (field-nya tinggal di sana);
 * - tanpa halaman konfigurasi (leveling, economy, starboard, automod) ->
 *   halaman Plugins dengan query ?tab=<grup>.
 */
export default function DashboardShell({ guildName, guildIconUrl, navItems, children }: Props) {
  const { dict } = useI18n();
  const [open, setOpen] = useState(false);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  // A11y: saat drawer ditutup, fokus kembali ke tombol hamburger.
  const close = () => {
    setOpen(false);
    menuButtonRef.current?.focus();
  };

  // R-32: drawer bisa ditutup dengan Escape; kunci scroll body saat terbuka.
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
  }, [open]);

  // A11y: saat drawer dibuka, pindahkan fokus ke elemen pertama di dalam
  // panel; trap Tab di dalam drawer sampai ditutup (fokus tak boleh nyasar
  // ke konten di belakang overlay).
  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;
    const focusables = () =>
      [...panel.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )].filter((el) => el.offsetParent !== null);
    // Fokus awal: elemen fokusable pertama (tombol kembali / link pertama).
    const first = focusables()[0];
    first?.focus();
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

  const topItems: SidebarEntry[] = [
    { href: hrefFor(""), label: sub.plugins, icon: "plugins" },
    { href: hrefFor("/overview"), label: sub.overview, icon: "overview" },
    { href: hrefFor("/leaderboard"), label: sub.leaderboard, icon: "leaderboard" },
    { href: hrefFor("/template"), label: dict.templates.navLabel, icon: "templates" },
    { href: hrefFor("/settings"), label: sub.settings, icon: "settings" },
  ];

  const pluginIcons: Record<string, SidebarIconId> = {
    welcome: "welcome",
    leveling: "leveling",
    selfroles: "reactionRoles",
    responder: "customCommands",
    economy: "economy",
    starboard: "starboard",
    giveaway: "giveaway",
    announcements: "announcements",
    customcmd: "customCommands",
    automod: "automod",
    slowmode: "automod",
    msglog: "modlog",
    embed: "embedBuilder",
    autopublish: "announcements",
    templates: "templates",
  };

  /** Tujuan link per plugin; lihat komentar di atas untuk polanya. */
  const pluginHref = (id: string, configure: string | null, group: PluginGroup): string => {
    if (id === "welcome") return `${hrefFor("/settings")}#welcome`;
    if (configure) return hrefFor(`/${configure}`);
    return `${homeHref}?tab=${group}`;
  };

  const groupTitle: Record<PluginGroup, string> = {
    essentials: pl.groupEssentials,
    engagement: pl.groupEngagement,
    moderation: pl.groupModeration,
    utilities: pl.groupUtilities,
  };

  const sections: SidebarSection[] = (["essentials", "engagement", "moderation", "utilities"] as PluginGroup[]).map(
    (group) => ({
      id: group,
      title: groupTitle[group],
      items: PLUGINS.filter((p) => p.group === group).map((p) => ({
        href: pluginHref(p.id, p.configure, p.group),
        label: cards[p.id]?.name ?? p.id,
        icon: pluginIcons[p.id] ?? "plugins",
      })),
    }),
  );

  const bottomItems: SidebarEntry[] = [
    { href: hrefFor("/modlog"), label: sub.modlog, icon: "modlog" },
    { href: hrefFor("/modul"), label: sub.modul, icon: "modules" },
  ];

  const sidebarProps = {
    guildName,
    guildIconUrl,
    topItems,
    sections,
    bottomItems,
    backHref: "/dashboard",
    backLabel: dict.nav.back,
    sectionLabel: sub.sectionLabel,
    serverMenuLabel: sub.serverMenuLabel,
    expandSectionLabel: sub.expandSection,
    collapseSectionLabel: sub.collapseSection,
  };

  return (
    <div className="min-h-screen bg-ink">
      {/* Topbar mobile: hanya tampil di bawah md */}
      <div className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-edge bg-ink px-3 md:hidden">
        <button
          ref={menuButtonRef}
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={open ? dict.dashboard.navClose : dict.dashboard.navOpen}
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
      </div>

      <div className="mx-auto flex max-w-7xl">
        {/* Sidebar desktop: kolom kiri sticky */}
        <aside className="hidden w-64 shrink-0 md:block">
          <div className="sticky top-0 h-screen border-r border-edge bg-panel">
            <Sidebar {...sidebarProps} />
          </div>
        </aside>

        {/* Konten halaman: padding konsisten + max-width terpusat, senada
            area konten referensi. Halaman di dalamnya tetap me-render
            kontennya sendiri. */}
        <main className="min-w-0 flex-1">
          <div className="mx-auto w-full max-w-5xl px-4 py-5 sm:px-6 md:px-8 md:py-7">
            {children}
          </div>
        </main>
      </div>

      {/* Drawer mobile */}
      {open && (
        <div
          className="fixed inset-0 z-40 md:hidden"
          role="dialog"
          aria-modal="true"
          aria-label={dict.guild.subnav.sectionLabel}
        >
          <button
            type="button"
            aria-label={dict.dashboard.navClose}
            onClick={close}
            className="absolute inset-0 h-full w-full cursor-default bg-ink/70"
          />
          <div
            ref={panelRef}
            className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-edge bg-panel"
          >
            <Sidebar {...sidebarProps} onNavigate={close} />
          </div>
        </div>
      )}
    </div>
  );
}
