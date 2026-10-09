import Image from "next/image";
import Link from "next/link";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import StatCard from "@/components/StatCard";
import { SignInButton } from "@/components/AuthButtons";
import { getDict, getLang } from "@/lib/i18n";
import { inviteUrl } from "@/lib/discord";
import { getSessionSafe } from "@/lib/access";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return {
    title: dict.landing.metaTitle,
    description: dict.landing.metaDescription,
  };
}

// Angka nyata hasil audit kode 2026-10-09 (diverifikasi ulang) — bukan karangan.
// - Slash command: 137 = 82 top-level non-grup + 55 subcommand (10 grup di-expand,
//   0 hidden, 1 context menu dikecualikan). Dihitung dengan parser AST yang
//   mereplikasi _kumpulkan_perintah() di bot/src/cogs/general.py
//   (grup tidak dihitung sendiri; hanya leaf /grup sub).
// - Plugin: 11 entri PLUGINS di dashboard/lib/plugins.ts.
// - Cog: 41 file .py non-underscore di bot/src/cogs/.
const NUM_COMMANDS = 137;
const NUM_PLUGINS = 11;
const NUM_COGS = 41;

const FEATURE_KEYS = ["welcome", "leveling", "selfroles", "automod", "economy", "giveaway"] as const;

export default async function Landing() {
  await connection(); // halaman dinamis: bahasa dari cookie, jangan di-prerender
  const session = await getSessionSafe();
  const lang = await getLang();
  const dict = getDict(lang);
  const l = dict.landing;
  const locale = lang === "id" ? "id-ID" : "en-US";
  const features = FEATURE_KEYS.map((k) => l.features[k]);

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-6xl px-4 pb-20">
        {/* Hero */}
        <section className="flex flex-col items-center py-16 text-center md:py-24">
          <Image src="/finch.png" alt={l.heroAlt} width={96} height={96} className="rounded-3xl" priority />
          <h1 className="mt-6 max-w-3xl text-3xl font-bold tracking-tight text-fg sm:text-4xl md:text-5xl">
            {l.heroTitle}
          </h1>
          <p className="mt-4 max-w-2xl text-base text-muted md:text-lg">{l.heroSubtitle}</p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <a
              href={inviteUrl()}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-6 py-3 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {l.ctaInvite}
            </a>
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-6 py-3 text-sm font-semibold text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {l.ctaDashboard}
            </Link>
          </div>
          {!session && (
            <div className="mt-4">
              <SignInButton />
            </div>
          )}
        </section>

        {/* Strip angka nyata */}
        <section aria-label={l.numbersAria} className="pb-16">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label={l.numCommands} value={NUM_COMMANDS.toLocaleString(locale)} />
            <StatCard label={l.numPlugins} value={NUM_PLUGINS.toLocaleString(locale)} />
            <StatCard label={l.numCogs} value={NUM_COGS.toLocaleString(locale)} />
          </div>
          <p className="mt-3 text-center text-xs text-muted">{l.numbersNote}</p>
        </section>

        {/* Fitur bergantian ala MEE6 */}
        <section aria-label={l.featuresAria} className="pb-16">
          <h2 className="text-center text-2xl font-bold tracking-tight text-fg md:text-3xl">
            {l.featuresTitle}
          </h2>
          <p className="mx-auto mt-2 max-w-2xl text-center text-sm text-muted">
            {l.featuresSubtitle}
          </p>
          <div className="mt-10 space-y-12 md:space-y-16">
            {features.map((f, i) => (
              <div
                key={f.title}
                className={`flex flex-col items-center gap-6 md:flex-row md:gap-10 ${
                  i % 2 === 1 ? "md:flex-row-reverse" : ""
                }`}
              >
                <div className="w-full md:w-1/2">
                  <div
                    aria-hidden="true"
                    className="flex min-h-44 items-center justify-center rounded-2xl border border-edge bg-panel py-10"
                  >
                    <span className="text-7xl md:text-8xl">{f.emoji}</span>
                  </div>
                </div>
                <div className="w-full md:w-1/2">
                  <h3 className="text-xl font-bold tracking-tight text-fg md:text-2xl">{f.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-muted md:text-base">{f.desc}</p>
                  <Link
                    href="/dashboard"
                    className="mt-4 inline-flex min-h-[44px] items-center text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                  >
                    {l.featureCta} →
                  </Link>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* Catatan kejujuran data */}
        <section aria-label={l.aboutAria} className="pb-16">
          <div className="rounded-xl border border-edge bg-panel p-6">
            <h2 className="text-lg font-bold text-fg">{l.aboutTitle}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{l.aboutBody}</p>
          </div>
        </section>

        {/* CTA akhir */}
        <section className="pb-4 text-center">
          <h2 className="text-2xl font-bold tracking-tight text-fg md:text-3xl">{l.finalTitle}</h2>
          <p className="mx-auto mt-2 max-w-xl text-sm text-muted">{l.finalSubtitle}</p>
          <div className="mt-6">
            <a
              href={inviteUrl()}
              className="inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-8 py-3 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
            >
              {l.ctaInvite}
            </a>
          </div>
        </section>
      </main>
      <footer className="border-t border-edge">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <p>{l.footerTagline}</p>
          <div className="flex flex-wrap items-center gap-4">
            <Link
              href="/dashboard"
              className="hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {l.footerDashboard}
            </Link>
            <a
              href={inviteUrl()}
              className="text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
            >
              {l.footerInvite}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
