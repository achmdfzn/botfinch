import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import GuildErrorState from "@/components/GuildErrorState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import StatCard from "@/components/StatCard";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { dbConfigured, latestSnapshot } from "@/lib/db";
import { getDict, getLang, fmt } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.overview.metaTitle} | Finch Dashboard` };
}

export default async function GuildOverviewPage({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const ov = dict.guild.overview;
  const sub = dict.guild.subnav;
  const locale = lang === "en" ? "en-US" : "id-ID";
  const session = await getSessionSafe();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.signinTitle} body={ov.signinBody} />
        </main>
      </div>
    );
  }

  // notFound() dipanggil di luar try/catch: ia melempar error kontrol
  // Next yang tidak boleh tertelan catch — guild tak ditemukan harus 404.
  let guilds: Awaited<ReturnType<typeof fetchUserGuilds>>;
  try {
    guilds = await fetchUserGuilds(session.accessToken);
  } catch {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.loadTitle} body={gc.loadBody} action={<ReloadButton />} />
        </main>
      </div>
    );
  }

  const mine = guilds.find((g) => g.id === guildId && canManage(g));
  if (!mine) notFound();

  if (!dbConfigured()) {
    return <GuildErrorState title={gc.dbTitle} body={ov.dbBody} />;
  }

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);

  const updatedAt = snap
    ? new Date(snap.pushed_at).toLocaleString(locale, {
        day: "numeric",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : "";

  const shortcuts = [
    { href: `/dashboard/${guildId}/modul`, title: sub.modul, desc: dict.guild.modul.subtitle },
    { href: `/dashboard/${guildId}/leaderboard`, title: sub.leaderboard, desc: dict.guild.leaderboard.subtitle },
    { href: `/dashboard/${guildId}/selfroles`, title: sub.selfroles, desc: dict.guild.selfroles.subtitle },
    { href: `/dashboard/${guildId}/responder`, title: sub.responder, desc: dict.guild.responder.subtitle },
    { href: `/dashboard/${guildId}/giveaway`, title: sub.giveaway, desc: dict.guild.giveaway.subtitle },
    { href: `/dashboard/${guildId}/embed`, title: sub.embed, desc: dict.guild.embed.subtitle },
    { href: `/dashboard/${guildId}/pengumuman`, title: sub.pengumuman, desc: dict.guild.pengumuman.subtitle },
    { href: `/dashboard/${guildId}/modlog`, title: sub.modlog, desc: dict.guild.modlog.subtitle },
  ];

  return (
    <div className="w-full">
      <PageHeader title={ov.metaTitle} description={ov.subtitle} />
      <div className="space-y-8">
        <section aria-label={ov.statsTitle}>
          <h2 className="text-base font-semibold text-fg">{ov.statsTitle}</h2>
          {!snapGuild ? (
            <div className="mt-3">
              <EmptyState title={ov.statsWaitingTitle} body={ov.statsWaitingBody} />
            </div>
          ) : (
            <>
              <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
                <StatCard label={ov.statMembers} value={snapGuild.member_count.toLocaleString(locale)} />
                <StatCard label={ov.statChannels} value={snapGuild.channels.length.toLocaleString(locale)} />
                <StatCard label={ov.statRoles} value={snapGuild.roles.length.toLocaleString(locale)} />
                <StatCard label={ov.statGiveaways} value={(snapGuild.giveaways ?? []).length.toLocaleString(locale)} />
              </div>
              <p className="mt-3 text-xs text-muted">{fmt(ov.updatedAt, { time: updatedAt })}</p>
            </>
          )}
        </section>

        <section aria-label={ov.shortcutsTitle}>
          <h2 className="text-base font-semibold text-fg">{ov.shortcutsTitle}</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {shortcuts.map((s) => (
              <Link
                key={s.href}
                href={s.href}
                className="rounded-xl border border-edge bg-panel p-4 transition-colors hover:border-brand focus-visible:outline-2 focus-visible:outline-brand sm:p-5"
              >
                <p className="flex items-center justify-between gap-3 text-sm font-semibold text-fg">
                  <span>{s.title}</span>
                  <span aria-hidden="true" className="shrink-0 text-brand">
                    →
                  </span>
                </p>
                <p className="mt-1 text-sm text-muted">{s.desc}</p>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}
