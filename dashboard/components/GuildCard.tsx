import Image from "next/image";
import Link from "next/link";
import { iconUrl, inviteUrl } from "@/lib/discord";

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
}

/** Kartu server vertikal: ikon bulat 72px di atas, nama, jumlah member, CTA full-width. */
export default function GuildCard({
  id,
  name,
  icon,
  memberText,
  inBot,
  openLabel,
  inviteLabel,
  noDataLabel,
}: Props) {
  const url = iconUrl(id, icon, 128);
  const initial = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <div className="flex h-full flex-col items-center rounded-2xl border border-edge bg-panel p-6 text-center transition-colors hover:border-brand/40">
      {url ? (
        <Image
          // unoptimized: icon 128px langsung dari CDN Discord, tanpa lewat
          // Image Optimization (di jaringan tertentu CDN resolve ke IP privat
          // dan diblokir proteksi SSRF Next.js)
          src={url}
          alt=""
          width={72}
          height={72}
          className="h-[72px] w-[72px] rounded-full"
          unoptimized
        />
      ) : (
        <div
          aria-hidden="true"
          className="flex h-[72px] w-[72px] items-center justify-center rounded-full bg-edge text-2xl font-bold text-fg"
        >
          {initial}
        </div>
      )}
      <p className="mt-4 w-full truncate text-sm font-semibold text-fg" title={name}>
        {name}
      </p>
      <p className="mt-1 w-full truncate text-xs text-muted">{memberText ?? noDataLabel}</p>
      <div className="mt-auto w-full pt-5">
        {inBot ? (
          <Link
            href={`/dashboard/${id}`}
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {openLabel}
          </Link>
        ) : (
          <a
            href={inviteUrl()}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-[44px] w-full items-center justify-center rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
          >
            {inviteLabel}
          </a>
        )}
      </div>
    </div>
  );
}
