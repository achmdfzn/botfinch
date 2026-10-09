import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import PluginCards, { type PluginCardData } from "@/components/PluginCards";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { dbConfigured, getStoredSettings } from "@/lib/db";
import { mergeSettings } from "@/lib/settings";
import { PLUGINS, TOGGLEABLE_PLUGINS, parsePluginTab } from "@/lib/plugins";
import { getDict, getLang, fmt } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.plugins.metaTitle} | Finch Dashboard` };
}

/**
 * Halaman Plugins utama per-server (dulu duplikat dengan /plugins).
 * /dashboard/[guildId]/plugins kini redirect ke sini.
 * Link sidebar plugin tanpa halaman konfigurasi memakai query ?tab=<grup>
 * untuk membuka tab kategori yang relevan.
 */
export default async function GuildPluginsHome({
  params,
  searchParams,
}: {
  params: Promise<{ guildId: string }>;
  searchParams: Promise<{ tab?: string }>;
}) {
  await connection(); // halaman dinamis: sesi + API Discord + DB, jangan di-prerender
  const { guildId } = await params;
  const { tab } = await searchParams;
  const initialTab = parsePluginTab(tab);
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const ov = dict.guild.overview;
  const pl = dict.guild.plugins;
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
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.dbTitle} body={ov.dbBody} />
        </main>
      </div>
    );
  }

  const stored = await getStoredSettings(guildId);
  const settings = mergeSettings(stored);

  // State awal toggle tiap plugin.
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

  // Label katalog plugin kini dari kamus (dict.guild.plugins).

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      {/* Header kompak: identitas server sudah ada di sidebar */}
      <PageHeader
        title={pl.metaTitle}
        description={fmt(ov.pluginActiveCount, { on: activePlugins, total: TOGGLEABLE_PLUGINS.length })}
      />
      <PluginCards
        guildId={guildId}
        plugins={pluginCards}
        initial={pluginInitial}
        initialTab={initialTab}
        groupTitles={{
          essentials: pl.groupEssentials,
          engagement: pl.groupEngagement,
          moderation: pl.groupModeration,
          utilities: pl.groupUtilities,
        }}
        labels={{
          tabAll: pl.tabAll,
          enable: pl.enable,
          disable: pl.disable,
          configure: pl.configure,
          statusActive: pl.statusActive,
          statusInactive: pl.statusInactive,
          saving: dict.guild.modul.saving,
          toggleError: dict.guild.modul.toggleError,
          toggleOn: dict.guild.modul.toggleOn,
          toggleOff: dict.guild.modul.toggleOff,
          tablistLabel: pl.tablistLabel,
          alwaysOn: pl.alwaysOn,
          pluginCount: pl.pluginCount,
          tabDesc: pl.tabDesc,
        }}
      />
    </div>
  );
}
