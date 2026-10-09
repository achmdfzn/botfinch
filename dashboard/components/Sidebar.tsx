"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";

export interface SidebarNavItem {
  href: string;
  label: string;
}

interface Props {
  guildName: string;
  guildIconUrl: string | null;
  items: SidebarNavItem[];
  backHref: string;
  backLabel: string;
  sectionLabel: string;
  /** Dipanggil saat link diklik; dipakai drawer mobile untuk menutup panel. */
  onNavigate?: () => void;
}

/**
 * Navigasi modul per-server gaya MEE6/Dyno: daftar vertikal.
 * Tanpa ikon: label 9 modul sudah deskriptif sendiri, ikon generik tanpa
 * relevansi justru jadi dekorasi (R-04). Link aktif ditandai bg-edge plus
 * indikator brand 3px di kiri, motif "indikator server terpilih" dari DESIGN.md.
 */
export default function Sidebar({
  guildName,
  guildIconUrl,
  items,
  backHref,
  backLabel,
  sectionLabel,
  onNavigate,
}: Props) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-3 border-b border-edge px-4 py-4">
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
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-fg">{guildName}</p>
          <Link
            href={backHref}
            onClick={onNavigate}
            className="mt-0.5 inline-block min-h-[24px] text-xs text-muted hover:text-fg hover:underline focus-visible:outline-2 focus-visible:outline-brand"
          >
            {backLabel}
          </Link>
        </div>
      </div>

      <nav aria-label={sectionLabel} className="min-h-0 flex-1 overflow-y-auto p-2">
        <ul className="flex flex-col gap-1">
          {items.map((item) => {
            const active = pathname === item.href || pathname === `${item.href}/`;
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={active ? "page" : undefined}
                  onClick={onNavigate}
                  className={`relative flex min-h-[44px] items-center rounded-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand ${
                    active ? "bg-edge text-fg" : "text-muted hover:bg-edge hover:text-fg"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`absolute left-0 top-1/2 h-6 w-[3px] -translate-y-1/2 rounded-full bg-brand ${
                      active ? "opacity-100" : "opacity-0"
                    }`}
                  />
                  {item.label}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
