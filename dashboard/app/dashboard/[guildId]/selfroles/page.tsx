import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import SelfRolesManager from "@/components/SelfRolesManager";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { getSelfRoles, latestSnapshot } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.selfroles.metaTitle} | Finch Dashboard` };
}

export default async function GuildSelfRoles({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const dict = getDict(await getLang());
  const g = dict.guild.selfroles;
  const { guildId } = await params;
  const session = await getSessionSafe();
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
          <EmptyState title={dict.guild.common.loadTitle} body={dict.guild.common.loadBody} action={<ReloadButton />} />
        </main>
      </div>
    );
  }

  const mine = guilds.find((g) => g.id === guildId && canManage(g));
  if (!mine) notFound();
  guildName = mine.name;

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);
  const awal = await getSelfRoles(guildId);

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
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
      <SelfRolesManager guildId={guildId} roles={snapGuild?.roles ?? []} initialRows={awal} />
    </div>
  );
}
