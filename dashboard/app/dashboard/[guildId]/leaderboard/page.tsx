import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import ReloadButton from "@/components/ReloadButton";
import LeaderboardTabs from "@/components/LeaderboardTabs";
import PageHeader from "@/components/PageHeader";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { latestSnapshot } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.leaderboard.metaTitle} | Finch Dashboard` };
}

export default async function GuildLeaderboard({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const session = await getSessionSafe();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.signinTitle} body={dict.guild.leaderboard.signinBody} />
        </main>
      </div>
    );
  }

  let guildName = guildId;
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
  guildName = mine.name;

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);

  return (
    <div className="w-full">
      <PageHeader
        title={guildName}
        description={dict.guild.leaderboard.subtitle}
        actions={
          <Link
            href="/dashboard"
            className="inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
          >
            {gc.backToGuilds}
          </Link>
        }
      />
      <div>
        {!snapGuild ? (
          <EmptyState title={gc.waitingTitle} body={dict.guild.leaderboard.waitingBody} />
        ) : (
          <LeaderboardTabs
            levels={snapGuild.leaderboards?.levels ?? []}
            coins={snapGuild.leaderboards?.coins ?? []}
            updatedAt={snap?.pushed_at ?? ""}
          />
        )}
      </div>
    </div>
  );
}
