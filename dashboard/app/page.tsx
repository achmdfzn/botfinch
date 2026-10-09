import Image from "next/image";
import Link from "next/link";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import StatCard from "@/components/StatCard";
import EmptyState from "@/components/EmptyState";
import { SignInButton } from "@/components/AuthButtons";
import { getDict, getLang } from "@/lib/i18n";
import { latestSnapshot } from "@/lib/db";
import { inviteUrl } from "@/lib/discord";

export const instant = false;

export default async function Landing() {
  await connection(); // halaman dinamis: sesi + DB, jangan di-prerender
  const lang = await getLang();
  const dict = getDict(lang);
  const l = dict.landing;
  const locale = lang === "id" ? "id-ID" : "en-US";
  const snap = await latestSnapshot();
  const memberTotal = snap ? snap.guilds.reduce((s, g) => s + (g.member_count || 0), 0) : 0;
  const modules = [l.modules.welcome, l.modules.leveling, l.modules.economy, l.modules.automod, l.modules.starboard];

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-5xl px-4 pb-20">
        <section className="flex flex-col items-center py-16 text-center md:py-24">
          <Image src="/finch.png" alt={l.heroAlt} width={96} height={96} className="rounded-3xl" priority />
          <h1 className="mt-6 max-w-2xl text-3xl font-bold tracking-tight text-fg sm:text-4xl md:text-5xl">
            {l.heroTitle}
          </h1>
          <p className="mt-4 max-w-xl text-base text-muted">{l.heroSubtitle}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href={inviteUrl()}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-6 py-3 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {l.ctaInvite}
            </a>
            <SignInButton />
          </div>
        </section>

        <section aria-label={l.statsAria} className="pb-14">
          {snap ? (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <StatCard label={l.statServers} value={snap.guilds.length.toLocaleString(locale)} />
              <StatCard label={l.statMembers} value={memberTotal.toLocaleString(locale)} />
              <StatCard
                label={l.statUpdated}
                value={new Date(snap.pushed_at).toLocaleString(locale, {
                  day: "numeric",
                  month: "short",
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              />
            </div>
          ) : (
            <EmptyState title={l.statsEmptyTitle} body={l.statsEmptyBody} />
          )}
        </section>

        <section aria-label={l.modulesAria} className="pb-14">
          <h2 className="text-2xl font-bold tracking-tight text-fg">{l.modulesTitle}</h2>
          <p className="mt-2 max-w-2xl text-sm text-muted">{l.modulesSubtitle}</p>
          <dl className="mt-6 divide-y divide-edge rounded-xl border border-edge bg-panel">
            {modules.map((m) => (
              <div key={m.title} className="px-5 py-4 sm:flex sm:items-baseline sm:gap-6">
                <dt className="w-32 shrink-0 text-sm font-semibold text-brand">{m.title}</dt>
                <dd className="mt-1 text-sm text-fg sm:mt-0">{m.desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section aria-label={l.aboutAria} className="pb-4">
          <div className="rounded-xl border border-edge bg-panel p-6">
            <h2 className="text-lg font-bold text-fg">{l.aboutTitle}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{l.aboutBody}</p>
            <Link
              href="/dashboard"
              className="mt-4 inline-flex min-h-[44px] items-center rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
            >
              {l.aboutCta}
            </Link>
          </div>
        </section>
      </main>
      <footer className="border-t border-edge">
        <div className="mx-auto flex max-w-5xl flex-col gap-2 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>{l.footerTagline}</p>
          <a href={inviteUrl()} className="text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand">
            {l.footerInvite}
          </a>
        </div>
      </footer>
    </div>
  );
}
