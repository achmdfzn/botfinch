import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { latestSnapshot } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.modlog.metaTitle} | Finch Dashboard` };
}

interface ModLogEntry {
  user_name: string;
  mod_name: string;
  aksi: string;
  alasan: string;
  waktu: string;
}

function asEntries(raw: unknown): ModLogEntry[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter(
      (e): e is Record<string, unknown> =>
        typeof e === "object" && e !== null,
    )
    .map((e) => ({
      user_name: String(e.user_name ?? "-"),
      mod_name: String(e.mod_name ?? "-"),
      aksi: String(e.aksi ?? "-"),
      alasan: String(e.alasan ?? "-"),
      waktu: String(e.waktu ?? ""),
    }));
}

function formatWaktu(iso: string, locale: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}

export default async function GuildModlog({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const lang = await getLang();
  const dict = getDict(lang);
  const g = dict.guild.modlog;
  const locale = lang === "en" ? "en-US" : "id-ID";
  const { guildId } = await params;
  const session = await auth();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={dict.guild.common.signinTitle} body={g.signinBody} />
        </main>
      </div>
    );
  }

  let guildName = guildId;
  try {
    const guilds = await fetchUserGuilds(session.accessToken);
    const mine = guilds.find((g) => g.id === guildId && canManage(g));
    if (!mine) notFound();
    guildName = mine.name;
  } catch {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={dict.guild.common.loadTitle} body={dict.guild.common.loadBody} />
        </main>
      </div>
    );
  }

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);
  const entries = asEntries(snapGuild?.modlog);

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <PageHeader
          title={guildName}
          description={g.subtitle}
          actions={
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {dict.guild.common.backToGuilds}
            </Link>
          }
        />
        {!snapGuild ? (
          <EmptyState
            title={dict.guild.common.waitingTitle}
            body={g.waitingBody}
          />
        ) : entries.length === 0 ? (
          <EmptyState
            title={g.emptyTitle}
            body={g.emptyBody}
          />
        ) : (
          <>
            {/* Desktop: tabel penuh */}
            <div className="hidden overflow-x-auto rounded-xl border border-edge bg-panel md:block">
              <table className="w-full min-w-[640px] text-left text-sm">
                <thead>
                  <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
                    <th scope="col" className="px-5 py-3 font-medium">{g.colTime}</th>
                    <th scope="col" className="px-5 py-3 font-medium">{g.colAction}</th>
                    <th scope="col" className="px-5 py-3 font-medium">{g.colUser}</th>
                    <th scope="col" className="px-5 py-3 font-medium">{g.colMod}</th>
                    <th scope="col" className="px-5 py-3 font-medium">{g.colReason}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-edge">
                  {entries.map((e, i) => (
                    <tr key={i} className="align-top">
                      <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted">
                        {formatWaktu(e.waktu, locale)}
                      </td>
                      <td className="px-5 py-3 font-medium text-fg">{e.aksi}</td>
                      <td className="px-5 py-3 text-fg">{e.user_name}</td>
                      <td className="px-5 py-3 text-fg">{e.mod_name}</td>
                      <td className="px-5 py-3 text-muted">{e.alasan}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {/* Mobile: kartu per entri */}
            <ul className="space-y-3 md:hidden">
              {entries.map((e, i) => (
                <li key={i} className="rounded-xl border border-edge bg-panel p-4">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-semibold text-fg">{e.aksi}</p>
                    <p className="shrink-0 font-mono text-xs text-muted">{formatWaktu(e.waktu, locale)}</p>
                  </div>
                  <dl className="mt-3 space-y-1.5 text-sm">
                    <div className="flex gap-2">
                      <dt className="w-20 shrink-0 text-muted">{g.colUser}</dt>
                      <dd className="min-w-0 break-words text-fg">{e.user_name}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-20 shrink-0 text-muted">{g.colMod}</dt>
                      <dd className="min-w-0 break-words text-fg">{e.mod_name}</dd>
                    </div>
                    <div className="flex gap-2">
                      <dt className="w-20 shrink-0 text-muted">{g.colReason}</dt>
                      <dd className="min-w-0 break-words text-muted">{e.alasan}</dd>
                    </div>
                  </dl>
                </li>
              ))}
            </ul>
          </>
        )}
      </main>
    </div>
  );
}
