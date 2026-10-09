import Link from "next/link";
import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import ModuleToggles from "@/components/ModuleToggles";
import PageHeader from "@/components/PageHeader";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured, getStoredSettings } from "@/lib/db";
import { MODULES, mergeSettings } from "@/lib/settings";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.guild.modul.metaTitle} | Finch Dashboard` };
}

export default async function GuildModul({ params }: { params: Promise<{ guildId: string }> }) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const session = await auth();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.signinTitle} body={dict.guild.modul.signinBody} />
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
          <EmptyState title={gc.dbTitle} body={dict.guild.modul.dbBody} />
        </main>
      </div>
    );
  }

  const stored = await getStoredSettings(guildId);
  const settings = mergeSettings(stored);
  const toggles: Record<string, boolean> = {};
  for (const m of MODULES) {
    toggles[m.key] = settings[m.key] === true;
  }

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-10">
        <PageHeader
          title={guildName}
          description={dict.guild.modul.subtitle}
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
          <ModuleToggles guildId={guildId} modules={MODULES} initial={toggles} />
        </div>
      </main>
    </div>
  );
}
