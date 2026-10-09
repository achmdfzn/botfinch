import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import PageHeader from "@/components/PageHeader";
import GuildListSync, { type GuildLite } from "@/components/GuildListSync";
import EmptyState from "@/components/EmptyState";
import { SignInButton } from "@/components/AuthButtons";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { latestSnapshot } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.dashboard.metaTitle} | Finch Dashboard` };
}

export default async function Dashboard() {
  await connection(); // halaman dinamis: sesi + API Discord, jangan di-prerender
  const lang = await getLang();
  const dict = getDict(lang);
  const d = dict.dashboard;
  const session = await getSessionSafe();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={d.signinTitle} body={d.signinBody} action={<SignInButton />} />
        </main>
      </div>
    );
  }

  let manageable;
  try {
    const guilds = await fetchUserGuilds(session.accessToken);
    manageable = guilds.filter(canManage);
  } catch {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState
            title={d.loadTitle}
            body={d.loadBody}
            action={
              <Link
                href="/dashboard"
                className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {d.retry}
              </Link>
            }
          />
        </main>
      </div>
    );
  }

  const snap = await latestSnapshot();
  const botGuilds = new Map((snap?.guilds ?? []).map((g) => [g.id, g]));
  const inBot: GuildLite[] = [];
  const notInBot: GuildLite[] = [];
  for (const g of manageable) {
    const bg = botGuilds.get(g.id);
    if (bg) {
      inBot.push({ id: g.id, name: bg.name, icon: bg.icon, memberCount: bg.member_count });
    } else {
      notInBot.push({ id: g.id, name: g.name, icon: g.icon, memberCount: null });
    }
  }

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
        <PageHeader title={d.title} description={d.subtitle} />

        {manageable.length === 0 ? (
          <div className="mt-8">
            <EmptyState title={d.emptyTitle} body={d.emptyBody} />
          </div>
        ) : (
          <GuildListSync initialInBot={inBot} initialNotInBot={notInBot} initialHasSnapshot={snap !== null} />
        )}
      </main>
    </div>
  );
}
