"use client";

import { useEffect, useState, type ReactNode } from "react";
import Sidebar, { type SidebarNavItem, type SidebarEntry, type SidebarSection } from "@/components/Sidebar";
import { useI18n } from "@/components/I18nProvider";

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
 * Sidebar ala MEE6 dibangun di sini dari navItems (untuk href) + dict
 * (untuk label): item utama, seksi grup collapsible, lalu item bawah.
 */
export default function DashboardShell({ guildName, guildIconUrl, navItems, children }: Props) {
  const { dict } = useI18n();
  const [open, setOpen] = useState(false);
  const close = () => setOpen(false);

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
  }, [open ]);

  const sub = dict.guild.subnav;
  const cards = dict.guild.plugins.cards;

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
  ];

  const sections: SidebarSection[] = [
    {
      id: "essentials",
      title: dict.guild.plugins.groupEssentials,
      items: [
        { href: hrefFor("/settings"), label: cards.welcome.name, icon: "welcome" },
        { href: hrefFor("/settings"), label: cards.leveling.name, icon: "leveling" },
        { href: hrefFor("/selfroles"), label: cards.selfroles.name, icon: "reactionRoles" },
        { href: hrefFor("/responder"), label: cards.responder.name, icon: "customCommands" },
      ],
    },
    {
      id: "engagement",
      title: dict.guild.plugins.groupEngagement,
      items: [
        { href: hrefFor("/settings"), label: cards.economy.name, icon: "economy" },
        { href: hrefFor("/settings"), label: cards.starboard.name, icon: "starboard" },
        { href: hrefFor("/giveaway"), label: cards.giveaway.name, icon: "giveaway" },
        { href: hrefFor("/pengumuman"), label: cards.announcements.name, icon: "announcements" },
      ],
    },
    {
      id: "moderation",
      title: dict.guild.plugins.groupModeration,
      items: [
        { href: hrefFor("/settings"), label: cards.automod.name, icon: "automod" },
      ],
    },
    {
      id: "utilities",
      title: dict.guild.plugins.groupUtilities,
      items: [
        { href: hrefFor("/embed"), label: cards.embed.name, icon: "embedBuilder" },
        { href: hrefFor("/template"), label: cards.templates.name, icon: "templates" },
      ],
    },
  ];

  const bottomItems: SidebarEntry[] = [
    { href: hrefFor("/modlog"), label: sub.modlog, icon: "modlog" },
    { href: hrefFor("/modul"), label: sub.modul, icon: "modules" },
    { href: hrefFor("/settings"), label: sub.settings, icon: "settings" },
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

      <div className="mx-auto flex max-w-6xl">
        {/* Sidebar desktop: kolom kiri sticky */}
        <aside className="hidden w-60 shrink-0 md:block">
          <div className="sticky top-0 h-screen border-r border-edge bg-panel">
            <Sidebar {...sidebarProps} />
          </div>
        </aside>

        {/* Konten halaman */}
        <div className="min-w-0 flex-1">{children}</div>
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
          <div className="absolute inset-y-0 left-0 flex w-72 max-w-[85vw] flex-col border-r border-edge bg-panel">
            <Sidebar {...sidebarProps} onNavigate={close} />
          </div>
        </div>
      )}
    </div>
  );
}
