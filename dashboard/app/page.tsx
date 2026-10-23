import { connection } from "next/server";
import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import StatCard from "@/components/StatCard";
import { SignInButton } from "@/components/AuthButtons";
import { getDict, getLang } from "@/lib/i18n";
import { inviteUrl } from "@/lib/discord";
import { getSessionSafe } from "@/lib/access";
import { STATS } from "@/lib/stats";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const l = getDict(await getLang()).landing;
  return {
    title: l.metaTitle,
    description: l.metaDescription,
  };
}

const FEATURE_KEYS = ["welcome", "leveling", "selfroles", "automod", "economy", "giveaway", "customcmd"] as const;
type FeatureKey = (typeof FEATURE_KEYS)[number];

// Ikon SVG orisinal (geometris, stroke) untuk tiap fitur — digambar sendiri,
// bukan aset/logo MEE6.
function FeatureIcon({ name }: { name: FeatureKey }) {
  const common = {
    viewBox: "0 0 48 48",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 3,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": true,
  } as const;
  switch (name) {
    case "welcome":
      // Pintu terbuka + panah masuk: sambutan member baru.
      return (
        <svg {...common}>
          <path d="M10 8h16v32H10z" />
          <path d="M22 24h14M32 18l6 6-6 6" />
        </svg>
      );
    case "leveling":
      // Bintang naik: XP & level.
      return (
        <svg {...common}>
          <path d="M24 8l4.5 9.5L39 19l-7.5 7 2 10.5L24 31l-9.5 5.5 2-10.5L9 19l10.5-1.5z" />
        </svg>
      );
    case "selfroles":
      // Kisi 2x2: pilih role sendiri.
      return (
        <svg {...common}>
          <rect x="9" y="9" width="13" height="13" rx="3" />
          <rect x="26" y="9" width="13" height="13" rx="3" />
          <rect x="9" y="26" width="13" height="13" rx="3" />
          <rect x="26" y="26" width="13" height="13" rx="3" />
        </svg>
      );
    case "automod":
      // Perisai: moderasi.
      return (
        <svg {...common}>
          <path d="M24 6l14 5v10c0 9-6 15-14 19-8-4-14-10-14-19V11z" />
          <path d="M18 24l4 4 8-9" />
        </svg>
      );
    case "economy":
      // Koin: ekonomi.
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="16" />
          <path d="M24 16v16M18.5 20.5c1-2 3-3 5.5-3s4.5 1 5.5 3M18.5 27.5c1 2 3 3 5.5 3s4.5-1 5.5-3" />
        </svg>
      );
    case "giveaway":
      // Kotak hadiah: giveaway.
      return (
        <svg {...common}>
          <rect x="10" y="16" width="28" height="22" rx="2" />
          <path d="M8 24h32M24 16v22M24 16c-6 0-9-2.5-9-6 0-2.5 2-4 4-4 3 0 4 6 5 10zm0 0c6 0 9-2.5 9-6 0-2.5-2-4-4-4-3 0-4 6-5 10z" />
        </svg>
      );
    case "customcmd":
      // Keyboard: perintah kustom buatan member.
      return (
        <svg {...common}>
          <rect x="6" y="14" width="36" height="20" rx="4" />
          <path d="M12 22h4M20 22h4M28 22h8" />
          <path d="M14 29h20" />
        </svg>
      );
    default:
      // Tak terjangkau (FeatureKey exhaustive) — fallback ikon netral.
      return (
        <svg {...common}>
          <circle cx="24" cy="24" r="16" />
        </svg>
      );
  }
}

// Ilustrasi hero orisinal: kartu perintah + chip perintah Finch di langit malam.
// Komposisi abstrak buatan sendiri — bukan karakter/ilustrasi MEE6.
function HeroArt({ alt }: { alt: string }) {
  return (
    <div
      role="img"
      aria-label={alt}
      className="relative mx-auto w-full max-w-md overflow-hidden rounded-3xl border border-white/10 bg-white/5 p-6"
    >
      {/* Bintang-bintang */}
      <svg aria-hidden="true" viewBox="0 0 400 300" className="h-auto w-full">
        {[
          [30, 24], [90, 60], [150, 20], [220, 44], [290, 18],
          [350, 56], [380, 120], [60, 120], [130, 100], [330, 170],
        ].map(([x, y], i) => (
          <circle key={i} cx={x} cy={y} r={i % 3 === 0 ? 2.4 : 1.5} fill="#ffffff" opacity={0.5} />
        ))}
        {/* Kartu perintah utama */}
        <rect x="70" y="110" width="260" height="130" rx="16" fill="#ffffff" opacity="0.08" />
        <rect x="70" y="110" width="260" height="130" rx="16" fill="none" stroke="#2ec4b6" strokeWidth="2" opacity="0.7" />
        <circle cx="100" cy="140" r="10" fill="#2ec4b6" opacity="0.9" />
        <rect x="120" y="132" width="120" height="8" rx="4" fill="#ffffff" opacity="0.7" />
        <rect x="120" y="146" width="80" height="6" rx="3" fill="#ffffff" opacity="0.35" />
        <rect x="92" y="168" width="180" height="10" rx="5" fill="#2ec4b6" opacity="0.35" />
        <rect x="92" y="186" width="130" height="10" rx="5" fill="#ffffff" opacity="0.25" />
        <rect x="92" y="204" width="150" height="10" rx="5" fill="#ffffff" opacity="0.18" />
        {/* Chip perintah melayang */}
        <g>
          <rect x="20" y="70" width="96" height="34" rx="17" fill="#2ec4b6" />
          <text x="68" y="92" textAnchor="middle" fontSize="15" fontWeight="700" fill="#062a27">/daily</text>
        </g>
        <g>
          <rect x="286" y="60" width="100" height="34" rx="17" fill="#ffffff" opacity="0.12" />
          <text x="336" y="82" textAnchor="middle" fontSize="15" fontWeight="700" fill="#f4f4f5">Level up!</text>
        </g>
        <g>
          <rect x="240" y="248" width="110" height="34" rx="17" fill="#ffffff" opacity="0.12" />
          <text x="295" y="270" textAnchor="middle" fontSize="15" fontWeight="700" fill="#f4f4f5">+250 🪙</text>
        </g>
      </svg>
    </div>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 20 20"
      fill="none"
      stroke="currentColor"
      strokeWidth="2.5"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="h-4 w-4 shrink-0 text-brand"
    >
      <path d="M4 10.5l4 4 8-9" />
    </svg>
  );
}

export default async function Landing() {
  await connection(); // halaman dinamis: bahasa dari cookie, jangan di-prerender
  const session = await getSessionSafe();
  const lang = await getLang();
  const fullDict = getDict(lang);
  const l = fullDict.landing;
  const locale = lang === "id" ? "id-ID" : "en-US";

  return (
    <div>
      <SiteHeader />
      <main>
        {/*
          HERO — gelap permanen ala referensi (bukan token tema): seluruh teks
          di dalamnya memakai warna terang tetap agar kontras aman di dua mode.
        */}
        <section className="bg-[#0b0e14]">
          <div className="mx-auto grid max-w-6xl items-center gap-10 px-4 py-16 md:grid-cols-2 md:py-24">
            <div className="text-center md:text-left">
              <p className="inline-flex min-h-[44px] items-center rounded-full border border-white/15 bg-white/5 px-4 py-2 text-xs font-semibold tracking-wide text-[#a8adb8] uppercase">
                {l.heroBadge}
              </p>
              <h1 className="mt-5 text-4xl font-extrabold tracking-tight text-white sm:text-5xl">
                {l.heroTitle}
              </h1>
              <p className="mx-auto mt-4 max-w-xl text-base leading-relaxed text-[#a8adb8] md:mx-0 md:text-lg">
                {l.heroSubtitle}
              </p>
              <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row md:justify-start">
                <a
                  href={inviteUrl()}
                  className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-[#2ec4b6] px-7 py-3 text-sm font-bold text-[#062a27] hover:bg-[#25a89b] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                >
                  {l.ctaInvite}
                </a>
                <a
                  href="#fitur"
                  className="inline-flex min-h-[44px] items-center justify-center rounded-xl border border-white/20 bg-white/5 px-7 py-3 text-sm font-bold text-white hover:bg-white/10 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-white"
                >
                  {l.ctaFeatures}
                </a>
              </div>
              {!session && (
                <div className="mt-6 flex flex-col items-center gap-3 sm:flex-row md:justify-start">
                  <p className="text-sm text-[#a8adb8]">{l.signinPrompt}</p>
                  <SignInButton />
                </div>
              )}
            </div>
            <div className="flex flex-col items-center gap-6">
              <Image
                src="/finch.png"
                alt={l.heroAlt}
                width={120}
                height={120}
                className="rounded-3xl"
                priority
              />
              <HeroArt alt={l.heroArtAlt} />
            </div>
          </div>
        </section>

        {/* Strip angka nyata */}
        <section aria-label={l.numbersAria} className="mx-auto max-w-6xl px-4 py-14">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <StatCard label={l.numCommands} value={STATS.commands.toLocaleString(locale)} />
            <StatCard label={l.numPlugins} value={STATS.plugins.toLocaleString(locale)} />
            <StatCard label={l.numCogs} value={STATS.cogs.toLocaleString(locale)} />
          </div>
          <p className="mt-3 text-center text-xs text-muted">{l.numbersNote}</p>
        </section>

        {/* Fitur zig-zag */}
        <section id="fitur" aria-label={l.featuresAria} className="mx-auto max-w-6xl scroll-mt-20 px-4 pb-16">
          <h2 className="text-center text-2xl font-bold tracking-tight text-fg md:text-3xl">
            {l.featuresTitle}
          </h2>
          <p className="mx-auto mt-2 max-w-2xl text-center text-sm leading-relaxed text-muted md:text-base">
            {l.featuresSubtitle}
          </p>
          <div className="mt-10 space-y-12 md:space-y-16">
            {FEATURE_KEYS.map((key, i) => {
              const f = l.features[key];
              return (
                <div
                  key={key}
                  className={`flex flex-col items-center gap-6 md:flex-row md:gap-10 ${
                    i % 2 === 1 ? "md:flex-row-reverse" : ""
                  }`}
                >
                  <div className="w-full md:w-1/2">
                    <div
                      aria-hidden="true"
                      className="flex min-h-48 items-center justify-center overflow-hidden rounded-2xl border border-edge bg-panel py-10"
                    >
                      <span className="flex h-28 w-28 items-center justify-center rounded-3xl bg-brand/10 text-brand">
                        <span className="block h-16 w-16">
                          <FeatureIcon name={key} />
                        </span>
                      </span>
                    </div>
                  </div>
                  <div className="w-full md:w-1/2">
                    <h3 className="text-xl font-bold tracking-tight text-fg md:text-2xl">{f.title}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-muted md:text-base">{f.desc}</p>
                    <ul className="mt-4 space-y-2">
                      {f.points.map((p) => (
                        <li key={p} className="flex items-center gap-2 text-sm text-fg">
                          <CheckIcon />
                          <span>{p}</span>
                        </li>
                      ))}
                    </ul>
                    <Link
                      href="/dashboard"
                      className="mt-4 inline-flex min-h-[44px] items-center text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                    >
                      {l.featureCta} →
                    </Link>
                  </div>
                </div>
              );
            })}
          </div>
        </section>

        {/* CTA akhir */}
        <section className="mx-auto max-w-6xl px-4 pb-20">
          <div className="rounded-2xl border border-edge bg-panel px-6 py-12 text-center">
            <h2 className="text-2xl font-bold tracking-tight text-fg md:text-3xl">{l.finalTitle}</h2>
            <p className="mx-auto mt-2 max-w-xl text-sm leading-relaxed text-muted md:text-base">
              {l.finalSubtitle}
            </p>
            <div className="mt-6">
              <a
                href={inviteUrl()}
                className="inline-flex min-h-[44px] items-center justify-center rounded-xl bg-brand px-8 py-3 text-sm font-bold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {l.ctaInvite}
              </a>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-edge">
        <div className="mx-auto flex max-w-6xl flex-col gap-3 px-4 py-6 text-sm text-muted sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p>{l.footerTagline}</p>
            <p className="mt-1 text-xs">{l.footerRights}</p>
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <Link
              href="/dashboard"
              className="inline-flex min-h-[44px] items-center hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {l.footerDashboard}
            </Link>
            <Link
              href="/pricing"
              className="inline-flex min-h-[44px] items-center hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
            >
              {fullDict.nav.pricing}
            </Link>
            <a
              href={inviteUrl()}
              className="inline-flex min-h-[44px] items-center text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
            >
              {l.footerInvite}
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
