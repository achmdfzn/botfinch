import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import PluginBrowser, { type PluginCardData } from "@/components/PluginBrowser";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured, getStoredSettings } from "@/lib/db";
import { mergeSettings } from "@/lib/settings";
import { PLUGINS, TOGGLEABLE_PLUGINS } from "@/lib/plugins";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.plugins.metaTitle} | Finch Dashboard` };
}

export default async function GuildPlugins({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const pl = dict.guild.plugins;
  const session = await auth();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.signinTitle} body={pl.signinBody} />
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
          <EmptyState title={gc.dbTitle} body={pl.dbBody} />
        </main>
      </div>
    );
  }

  const stored = await getStoredSettings(guildId);
  const settings = mergeSettings(stored);
  const initial: Record<string, boolean> = {};
  for (const p of TOGGLEABLE_PLUGINS) {
    if (p.toggleKey) initial[p.toggleKey] = settings[p.toggleKey] === true;
  }

  const cards = dict.guild.plugins.cards as Record<string, { name: string; desc: string }>;
  const plugins: PluginCardData[] = PLUGINS.map((p) => ({
    id: p.id,
    emoji: p.emoji,
    group: p.group,
    toggleKey: p.toggleKey,
    configure: p.configure,
    name: cards[p.id]?.name ?? p.id,
    desc: cards[p.id]?.desc ?? "",
  }));

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 py-10">
        <PageHeader
          title={guildName}
          description={pl.subtitle}
          actions={
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {gc.backToGuilds}
            </Link>
          }
        />
        <PluginBrowser
          guildId={guildId}
          plugins={plugins}
          initial={initial}
          groupTitles={{
            essentials: pl.groupEssentials,
            engagement: pl.groupEngagement,
            moderation: pl.groupModeration,
            utilities: pl.groupUtilities,
          }}
          labels={{
            tabAll: pl.tabAll,
            configure: pl.configure,
            enable: pl.enable,
            disable: pl.disable,
            saving: dict.guild.modul.saving,
            toggleError: dict.guild.modul.toggleError,
            toggleOn: dict.guild.modul.toggleOn,
            toggleOff: dict.guild.modul.toggleOff,
            statusActive: pl.statusActive,
            statusInactive: pl.statusInactive,
          }}
        />
      </main>
    </div>
  );
}
