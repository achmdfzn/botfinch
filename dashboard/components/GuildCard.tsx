"use client";

import Image from "next/image";
import Link from "next/link";
import { iconUrl, inviteUrl } from "@/lib/discord";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface Props {
  id: string;
  name: string;
  icon: string | null;
  /** Teks jumlah member yang sudah diformat sesuai bahasa; null = belum ada data. */
  memberText: string | null;
  inBot: boolean;
  openLabel: string;
  inviteLabel: string;
  noDataLabel: string;
  /**
   * True bila user adalah owner server ini -> badge "Owner".
   * Default false -> badge "Kelola Server" (semua server yang tampil di
   * halaman ini lolos filter izin Kelola Server).
   */
  isOwner?: boolean;
}

/**
 * Hash deterministik dari ID guild -> hue, dipakai untuk gradient banner
 * orisinal tiap server (Discord /users/@me/guilds tidak mengembalikan
 * banner, jadi banner selalu dibuat lokal — bukan aset pihak ketiga).
 */
function bannerGradient(guildId: string): string {
  let h = 0;
  for (let i = 0; i < guildId.length; i++) {
    h = (h * 31 + guildId.charCodeAt(i)) >>> 0;
  }
  const hue = h % 360;
  return `linear-gradient(135deg, hsl(${hue} 45% 34%), hsl(${(hue + 45) % 360} 55% 16%))`;
}

/**
 * Kartu server ala halaman pilih server: banner gradient di atas, ikon
 * lingkaran menumpuk di batas banner, nama + badge peran, lalu CTA.
 * Satu kolom di HP (360px aman), 2-3 kolom di layar lebih lebar
 * (diatur grid oleh pemanggil).
 */
export default function GuildCard({
  id,
  name,
  icon,
  memberText,
  inBot,
  openLabel,
  inviteLabel,
  noDataLabel,
  isOwner = false,
}: Props) {
  const { dict } = useI18n();
  const fs = dict.dashboard;
  const url = iconUrl(id, icon, 128);
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-2xl border border-edge bg-panel transition-colors hover:border-brand/40">
      {/* Banner orisinal: gradient deterministik + pola titik halus */}
      <div className="relative h-24 w-full shrink-0" style={{ background: bannerGradient(id) }} aria-hidden="true">
        <div
          className="absolute inset-0 opacity-15"
          style={{
            backgroundImage: "radial-gradient(circle at 1px 1px, #ffffff 1px, transparent 0)",
            backgroundSize: "18px 18px",
          }}
        />
      </div>

      {/* Ikon lingkaran menumpuk di batas bawah banner */}
      <div className="-mt-9 flex justify-center">
        {url ? (
          <Image
            // unoptimized: icon 128px langsung dari CDN Discord, tanpa lewat
            // Image Optimization (di jaringan tertentu CDN resolve ke IP privat
            // dan diblokir proteksi SSRF Next.js)
            src={url}
            alt=""
            width={72}
            height={72}
            className="h-[72px] w-[72px] rounded-full ring-4 ring-panel"
            unoptimized
          />
        ) : (
          <div
            aria-hidden="true"
            className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-brand/15 text-2xl font-bold text-brand ring-4 ring-panel"
          >
            {initial}
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col items-center px-5 pb-5 pt-3 text-center">
        <h3 className="w-full truncate text-sm font-semibold text-fg" title={name}>
          {name}
        </h3>
        <span className="mt-2 inline-flex items-center rounded-full bg-edge px-2.5 py-1 text-[11px] font-medium text-muted">
          {isOwner ? fs.badgeOwner : fs.badgeManager}
        </span>
        <p className="mt-1.5 w-full truncate text-xs text-muted">{memberText ?? noDataLabel}</p>

        <div className="mt-4 w-full">
          {inBot ? (
            <Link
              href={`/dashboard/${id}`}
              aria-label={fmt(fs.openAria, { name })}
              className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {openLabel}
            </Link>
          ) : (
            <a
              href={inviteUrl()}
              target="_blank"
              rel="noopener noreferrer"
              aria-label={fmt(fs.inviteAria, { name })}
              className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
            >
              {inviteLabel}
            </a>
          )}
        </div>
      </div>
    </article>
  );
}
