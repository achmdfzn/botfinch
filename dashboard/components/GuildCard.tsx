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
  manageLabel: string;
  inviteLabel: string;
  noDataLabel: string;
}

/** Kartu server: ikon + nama (truncate, tidak overflow di 360px) + aksi 44px. */
export default function GuildCard({
  id,
  name,
  icon,
  memberText,
  inBot,
  manageLabel,
  inviteLabel,
  noDataLabel,
}: Props) {
  const url = iconUrl(id, icon, 128);
  return (
    <div className="flex items-center gap-4 rounded-xl border border-edge bg-panel p-4">
      {url ? (
        <Image
          // unoptimized: icon 128px langsung dari CDN Discord, tanpa lewat
          // Image Optimization (di jaringan tertentu CDN resolve ke IP privat
          // dan diblokir proteksi SSRF Next.js)
          src={url}
          alt=""
          width={48}
          height={48}
          className="h-12 w-12 shrink-0 rounded-full"
          unoptimized
        />
      ) : (
        <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-edge text-lg font-bold text-fg">
          {name.slice(0, 1).toUpperCase()}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-semibold text-fg">{name}</p>
        <p className="truncate text-xs text-muted">{memberText ?? noDataLabel}</p>
      </div>
      {inBot ? (
        <Link
          href={`/dashboard/${id}`}
          className="inline-flex min-h-[44px] shrink-0 items-center rounded-lg bg-brand px-4 py-2 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {manageLabel}
        </Link>
      ) : (
        <a
          href={inviteUrl()}
          className="inline-flex min-h-[44px] shrink-0 items-center rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
        >
          {inviteLabel}
        </a>
      )}
    </div>
  );
}
