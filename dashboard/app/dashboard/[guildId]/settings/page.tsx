import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import SettingsForm from "@/components/SettingsForm";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured, getStoredSettings, latestSnapshot } from "@/lib/db";
import { MODULES, mergeSettings } from "@/lib/settings";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.subnav.settings} | Finch Dashboard` };
}

export default async function GuildSettingsPage({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const ov = dict.guild.overview;
  const sub = dict.guild.subnav;
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

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 py-10">
        <PageHeader title={sub.settings} description={ov.settingsDesc} />
        {!snapGuild && (
          <div className="mb-4">
            <EmptyState title={gc.waitingTitle} body={ov.waitingBody} />
          </div>
        )}
        <SettingsForm
          guildId={guildId}
          guildName={guildName}
          modules={MODULES}
          initial={settings}
          channels={snapGuild?.channels ?? []}
          roles={snapGuild?.roles ?? []}
        />
      </main>
    </div>
  );
}
