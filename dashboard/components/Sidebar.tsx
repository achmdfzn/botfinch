"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { fmt } from "@/lib/i18n/client";

export interface SidebarNavItem {
  href: string;
  label: string;
}

/**
 * ID ikon SVG monochrome (currentColor) per item navigasi.
 * Ikon digambar inline di bawah — tanpa emoji, satu warna brand via token.
 */
export type SidebarIconId =
  | "plugins"
  | "overview"
  | "leaderboard"
  | "welcome"
  | "leveling"
  | "reactionRoles"
  | "customCommands"
  | "economy"
  | "starboard"
  | "giveaway"
  | "announcements"
  | "automod"
  | "embedBuilder"
  | "templates"
  | "modlog"
  | "modules"
  | "settings";

export interface SidebarEntry {
  href: string;
  label: string;
  icon: SidebarIconId;
}

export interface SidebarSection {
  id: string;
  title: string;
  items: SidebarEntry[];
}

interface Props {
  guildName: string;
  guildIconUrl: string | null;
  /** Item utama di atas seksi: Plugins, Overview, Leaderboard. */
  topItems: SidebarEntry[];
  /** Seksi grup collapsible ala MEE6: Esensial, Engagement & Fun, ... */
  sections: SidebarSection[];
  /** Item di bawah seksi: Mod Log, Modules, Settings. */
  bottomItems: SidebarEntry[];
  backHref: string;
  backLabel: string;
  sectionLabel: string;
  serverMenuLabel: string;
  /** Template aria-label toggle seksi; boleh mengandung {name}. */
  expandSectionLabel: string;
  collapseSectionLabel: string;
  /** Dipanggil saat link diklik; dipakai drawer mobile untuk menutup panel. */
  onNavigate?: () => void;
}

const ICON_PATHS: Record<SidebarIconId, React.ReactNode> = {
  plugins: (
    <>
      <rect x="4" y="4" width="7" height="7" rx="1.5" />
      <rect x="13" y="4" width="7" height="7" rx="1.5" />
      <rect x="4" y="13" width="7" height="7" rx="1.5" />
      <rect x="13" y="13" width="7" height="7" rx="1.5" />
    </>
  ),
  overview: (
    <>
      <path d="M4 15a8 8 0 1 1 16 0" />
      <path d="M12 15l4.5-4.5" />
      <path d="M3 19h18" />
    </>
  ),
  leaderboard: (
    <>
      <path d="M8 4h8v5a4 4 0 0 1-8 0V4z" />
      <path d="M8 5.5H5a3 3 0 0 0 3.2 4.8M16 5.5h3a3 3 0 0 1-3.2 4.8" />
      <path d="M12 13v4" />
      <path d="M8.5 20h7M9.5 17h5" />
    </>
  ),
  welcome: (
    <>
      <path d="M14 4h5a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-5" />
      <path d="M3 12h11" />
      <path d="M10.5 8.5L14 12l-3.5 3.5" />
    </>
  ),
  leveling: (
    <>
      <path d="M3 17l6-6 4 4 8-8" />
      <path d="M15 7h6v6" />
    </>
  ),
  reactionRoles: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M8.5 10.5h.01M15.5 10.5h.01" />
      <path d="M8.5 14.5a4 4 0 0 0 7 0" />
    </>
  ),
  customCommands: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M7 9.5l3 3-3 3" />
      <path d="M12.5 15.5H17" />
    </>
  ),
  economy: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="4" />
    </>
  ),
  starboard: (
    <path d="M12 4l2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-3-5.4 3 1.1-6L3.2 10.4l6.1-.8L12 4z" />
  ),
  giveaway: (
    <>
      <rect x="4" y="9" width="16" height="11" rx="1.5" />
      <path d="M12 9v11M4 13.5h16" />
      <path d="M12 9C8 9 6.5 7.5 6.5 5.5 6.5 3.7 8 3 9 3.7 10.5 4.7 12 9 12 9z" />
      <path d="M12 9c4 0 5.5-1.5 5.5-3.5 0-1.8-1.5-2.5-2.5-1.8C13.5 4.7 12 9 12 9z" />
    </>
  ),
  announcements: (
    <>
      <path d="M4 10.5v4h2.5L15 19V6l-8.5 4.5H4z" />
      <path d="M18 9.5a4.5 4.5 0 0 1 0 6" />
      <path d="M8.5 16.5V20" />
    </>
  ),
  automod: (
    <>
      <path d="M12 3l7 3v5c0 5-3 8-7 10-4-2-7-5-7-10V6l7-3z" />
      <path d="M9 12l2 2 4-4" />
    </>
  ),
  embedBuilder: (
    <>
      <path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1z" />
      <path d="M14.5 6.5l3 3" />
    </>
  ),
  templates: (
    <>
      <path d="M12 3l9 5-9 5-9-5 9-5z" />
      <path d="M3.5 13L12 17.5 20.5 13" />
    </>
  ),
  modlog: (
    <>
      <rect x="5" y="4.5" width="14" height="16.5" rx="2" />
      <path d="M9 4.5a3 3 0 0 1 6 0" />
      <path d="M9 11.5h6M9 15.5h6" />
    </>
  ),
  modules: (
    <>
      <path d="M4 7h16M4 12h16M4 17h16" />
      <circle cx="10" cy="7" r="2.2" />
      <circle cx="15" cy="12" r="2.2" />
      <circle cx="9" cy="17" r="2.2" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M17 12h2.5M15.5 15.5l1.8 1.8M12 17v2.5M8.5 15.5l-1.8 1.8M7 12H4.5M8.5 8.5L6.7 6.7M12 7V4.5M15.5 8.5l1.8-1.8" />
    </>
  ),
};

function SidebarIcon({ id, className }: { id: SidebarIconId; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className ?? "h-5 w-5 shrink-0"}
    >
      {ICON_PATHS[id]}
    </svg>
  );
}

function isActivePath(pathname: string, href: string): boolean {
  return pathname === href || pathname === `${href}/`;
}

function EntryLink({
  entry,
  pathname,
  onNavigate,
}: {
  entry: SidebarEntry;
  pathname: string;
  onNavigate?: () => void;
}) {
  const active = isActivePath(pathname, entry.href);
  return (
    <Link
      href={entry.href}
      aria-current={active ? "page" : undefined}
      onClick={onNavigate}
      className={`relative flex min-h-[44px] items-center gap-3 rounded-lg py-2.5 pl-4 pr-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand ${
        active ? "bg-edge text-fg" : "text-muted hover:bg-edge hover:text-fg"
      }`}
    >
      <span
        aria-hidden="true"
        className={`absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-full bg-brand ${
          active ? "opacity-100" : "opacity-0"
        }`}
      />
      <SidebarIcon id={entry.icon} />
      <span className="truncate">{entry.label}</span>
    </Link>
  );
}

/**
 * Navigasi modul per-server ala MEE6: header server dengan dropdown,
 * item berikon, dan seksi grup collapsible.
 * Link aktif ditandai bg-edge plus indikator brand 3px di kiri,
 * motif "indikator server terpilih" dari DESIGN.md.
 */
export default function Sidebar({
  guildName,
  guildIconUrl,
  topItems,
  sections,
  bottomItems,
  backHref,
  backLabel,
  sectionLabel,
  serverMenuLabel,
  expandSectionLabel,
  collapseSectionLabel,
  onNavigate,
}: Props) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuWrapRef = useRef<HTMLDivElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  // Seksi default expanded; true = collapsed.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  // Dropdown server: Escape menutup + fokus kembali ke tombol; klik di luar menutup.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMenuOpen(false);
        menuButtonRef.current?.focus();
      }
    };
    const onPointer = (e: MouseEvent) => {
      if (menuWrapRef.current && !menuWrapRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onPointer);
    };
  }, [menuOpen ]);

  const entryKey = (entry: SidebarEntry) => `${entry.href}#${entry.label}`;

  return (
    <div className="flex h-full flex-col">
      {/* Header server ala MEE6: ikon + nama + chevron pembuka menu */}
      <div ref={menuWrapRef} className="relative border-b border-edge px-3 py-3">
        <div className="flex items-center gap-2">
          {guildIconUrl ? (
            <Image
              // unoptimized: ikon langsung dari CDN Discord, tanpa lewat
              // Image Optimization (lihat alasan di GuildCard)
              src={guildIconUrl}
              alt=""
              width={40}
              height={40}
              className="h-10 w-10 shrink-0 rounded-full"
              unoptimized
            />
          ) : (
            <div
              aria-hidden="true"
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-edge text-base font-bold text-fg"
            >
              {guildName.slice(0, 1).toUpperCase()}
            </div>
          )}
          <button
            ref={menuButtonRef}
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            aria-expanded={menuOpen}
            aria-haspopup="menu"
            aria-label={serverMenuLabel}
            className="flex min-h-[44px] min-w-0 flex-1 items-center justify-between gap-2 rounded-lg px-2 text-left hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
          >
            <span className="truncate text-sm font-semibold text-fg">{guildName}</span>
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
              className={`h-4 w-4 shrink-0 text-muted transition-transform ${menuOpen ? "rotate-180" : ""}`}
            >
              <path d="M6 9l6 6 6-6" />
            </svg>
          </button>
        </div>
        {menuOpen && (
          <div
            role="menu"
            aria-label={serverMenuLabel}
            className="absolute inset-x-3 top-full z-10 mt-1 rounded-lg border border-edge bg-panel p-1 shadow-lg"
          >
            <Link
              role="menuitem"
              href={backHref}
              onClick={() => {
                setMenuOpen(false);
                onNavigate?.();
              }}
              className="flex min-h-[44px] items-center rounded-md px-3 text-sm font-medium text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {backLabel}
            </Link>
          </div>
        )}
      </div>

      <nav aria-label={sectionLabel} className="min-h-0 flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-1">
          {topItems.map((entry) => (
            <li key={entryKey(entry)}>
              <EntryLink entry={entry} pathname={pathname} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>

        {sections.map((section) => {
          const isCollapsed = collapsed[section.id] === true;
          const sectionListId = `sidebar-section-${section.id}`;
          return (
            <div key={section.id} className="mt-3">
              <button
                type="button"
                aria-expanded={!isCollapsed}
                aria-controls={sectionListId}
                aria-label={fmt(isCollapsed ? expandSectionLabel : collapseSectionLabel, {
                  name: section.title,
                })}
                onClick={() =>
                  setCollapsed((prev) => ({ ...prev, [section.id]: !isCollapsed }))
                }
                className="flex min-h-[44px] w-full items-center justify-between gap-2 rounded-lg px-4 py-2 text-xs font-semibold uppercase tracking-wider text-muted hover:bg-edge hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
              >
                <span className="truncate">{section.title}</span>
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                  className={`h-4 w-4 shrink-0 transition-transform ${isCollapsed ? "-rotate-90" : ""}`}
                >
                  <path d="M6 9l6 6 6-6" />
                </svg>
              </button>
              {!isCollapsed && (
                <ul id={sectionListId} className="flex flex-col gap-1">
                  {section.items.map((entry) => (
                    <li key={entryKey(entry)}>
                      <EntryLink entry={entry} pathname={pathname} onNavigate={onNavigate} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}

        <ul className="mt-3 flex flex-col gap-1 border-t border-edge pt-3">
          {bottomItems.map((entry) => (
            <li key={entryKey(entry)}>
              <EntryLink entry={entry} pathname={pathname} onNavigate={onNavigate} />
            </li>
          ))}
        </ul>
      </nav>
    </div>
  );
}
