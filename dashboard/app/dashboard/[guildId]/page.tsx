import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PluginBrowser, { type PluginCardData } from "@/components/PluginBrowser";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds, iconUrl } from "@/lib/discord";
import { dbConfigured, getStoredSettings, latestSnapshot } from "@/lib/db";
import { mergeSettings } from "@/lib/settings";
import { PLUGINS, TOGGLEABLE_PLUGINS } from "@/lib/plugins";
import { getDict, getLang, fmt } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.plugins.metaTitle} | Finch Dashboard` };
}

export default async function GuildPluginsHome({ params }: { params: Promise<{ guildId: string }> }) {
  await connection(); // halaman dinamis: sesi + API Discord + DB, jangan di-prerender
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const ov = dict.guild.overview;
  const pl = dict.guild.plugins;
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
  let guildIconUrl: string | null = null;
  try {
    const guilds = await fetchUserGuilds(session.accessToken);
    const mine = guilds.find((g) => g.id === guildId && canManage(g));
    if (!mine) notFound();
    guildName = mine.name;
    guildIconUrl = iconUrl(guildId, mine.icon, 128);
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

  await latestSnapshot();
  const stored = await getStoredSettings(guildId);
  const settings = mergeSettings(stored);

  // Data untuk PluginBrowser: pemetaan sama persis dengan /dashboard/[guildId]/plugins
  const pluginInitial: Record<string, boolean> = {};
  for (const p of TOGGLEABLE_PLUGINS) {
    if (p.toggleKey) pluginInitial[p.toggleKey] = settings[p.toggleKey] === true;
  }
  const cards = dict.guild.plugins.cards as Record<string, { name: string; desc: string }>;
  const pluginCards: PluginCardData[] = PLUGINS.map((p) => ({
    id: p.id,
    emoji: p.emoji,
    group: p.group,
    toggleKey: p.toggleKey,
    configure: p.configure,
    name: cards[p.id]?.name ?? p.id,
    desc: cards[p.id]?.desc ?? "",
  }));

  const activePlugins = TOGGLEABLE_PLUGINS.filter(
    (p) => p.toggleKey && settings[p.toggleKey] === true,
  ).length;

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 py-10">
        {/* Blok sambutan: ikon + nama server + status plugin */}
        <section aria-label={ov.welcomeAria} className="mb-8">
          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-edge bg-panel p-4 sm:p-5">
            {guildIconUrl ? (
              <Image
                // unoptimized: ikon langsung dari CDN Discord, tanpa lewat
                // Image Optimization (lihat alasan di GuildCard)
                src={guildIconUrl}
                alt=""
                width={64}
                height={64}
                className="h-16 w-16 shrink-0 rounded-2xl"
                unoptimized
              />
            ) : (
              <div
                aria-hidden="true"
                className="flex h-16 w-16 shrink-0 items-center justify-center rounded-2xl bg-edge text-2xl font-bold text-fg"
              >
                {guildName.slice(0, 1).toUpperCase()}
              </div>
            )}
            <div className="min-w-0 flex-1 basis-48">
              <h1 className="truncate text-xl font-bold tracking-tight text-fg sm:text-2xl">
                {guildName}
              </h1>
              <p className="mt-1 text-sm text-muted">
                {fmt(ov.pluginActiveCount, { on: activePlugins, total: TOGGLEABLE_PLUGINS.length })}
              </p>
            </div>
          </div>
          <Link
            href="/dashboard"
            className="mt-3 inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
          >
            {gc.backToGuilds}
          </Link>
        </section>
        <PluginBrowser
          guildId={guildId}
          plugins={pluginCards}
          initial={pluginInitial}
          groupTitles={{
            essentials: pl.groupEssentials,
            engagement: pl.groupEngagement,
            moderation: pl.groupModeration,
            utilities: pl.groupUtilities,
          }}
          heading={pl.metaTitle}
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
