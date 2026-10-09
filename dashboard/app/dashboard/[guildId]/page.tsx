import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import SettingsForm from "@/components/SettingsForm";
import GuildTabs from "@/components/GuildTabs";
import PageHeader from "@/components/PageHeader";
import StatCard from "@/components/StatCard";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured, getStoredSettings, latestSnapshot } from "@/lib/db";
import { MODULES, mergeSettings } from "@/lib/settings";
import { getDict, getLang, fmt } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.overview.metaTitle} | Finch Dashboard` };
}

export default async function GuildOverview({ params }: { params: Promise<{ guildId: string }> }) {
  await connection(); // halaman dinamis: sesi + API Discord + DB, jangan di-prerender
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const ov = dict.guild.overview;
  const sub = dict.guild.subnav;
  const locale = lang === "en" ? "en-US" : "id-ID";
  const session = await auth();
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
          <EmptyState title={gc.loadTitle} body={gc.loadBody} />
        </main>
      </div>
    );
  }

  if (!dbConfigured()) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.dbTitle} body={ov.dbBody} />
        </main>
      </div>
    );
  }

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);
  const stored = await getStoredSettings(guildId);
  const settings = mergeSettings(stored);

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
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-5xl px-4 py-10">
        <PageHeader
          title={guildName}
          description={ov.subtitle}
          actions={
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {gc.backToGuilds}
            </Link>
          }
        />
        <GuildTabs
          overview={
            <div className="space-y-8">
              <section aria-label={ov.statsTitle}>
                <h2 className="text-sm font-semibold text-fg">{ov.statsTitle}</h2>
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
                <h2 className="text-sm font-semibold text-fg">{ov.shortcutsTitle}</h2>
                <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2">
                  {shortcuts.map((s) => (
                    <Link
                      key={s.href}
                      href={s.href}
                      className="rounded-xl border border-edge bg-panel p-4 transition-colors hover:border-brand focus-visible:outline-2 focus-visible:outline-brand sm:p-5"
                    >
                      <p className="text-sm font-semibold text-fg">{s.title}</p>
                      <p className="mt-1 text-sm text-muted">{s.desc}</p>
                    </Link>
                  ))}
                </div>
              </section>
            </div>
          }
          settings={
            <div>
              <h2 className="text-sm font-semibold text-fg">{ov.settingsTitle}</h2>
              <p className="mt-1 text-sm text-muted">{ov.settingsDesc}</p>
              {!snapGuild && (
                <div className="mt-4">
                  <EmptyState title={gc.waitingTitle} body={ov.waitingBody} />
                </div>
              )}
              <div className="mt-4">
                <SettingsForm
                  guildId={guildId}
                  guildName={guildName}
                  modules={MODULES}
                  initial={settings}
                  channels={snapGuild?.channels ?? []}
                  roles={snapGuild?.roles ?? []}
                />
              </div>
            </div>
          }
        />
      </main>
    </div>
  );
}
