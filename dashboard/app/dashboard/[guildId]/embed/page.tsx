import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import EmbedBuilder from "@/components/EmbedBuilder";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured, latestSnapshot } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.embed.metaTitle} | Finch Dashboard` };
}

export default async function GuildEmbed({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const dict = getDict(await getLang());
  const g = dict.guild.embed;
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

  if (!dbConfigured()) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={dict.guild.common.dbTitle} body={g.dbBody} />
        </main>
      </div>
    );
  }

  const snap = await latestSnapshot();
  const snapGuild = snap?.guilds.find((g) => g.id === guildId);

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <Link href="/dashboard" className="text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand">
          {dict.nav.back}
        </Link>
        <div className="mt-3">
          <PageHeader title={guildName} description={g.subtitle} />
        </div>
        <EmbedBuilder guildId={guildId} channels={snapGuild?.channels ?? []} />
      </main>
    </div>
  );
}
