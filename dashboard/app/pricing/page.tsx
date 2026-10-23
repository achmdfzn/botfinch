import { connection } from "next/server";
import type { Metadata } from "next";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import { getDict, getLang } from "@/lib/i18n";
import { inviteUrl } from "@/lib/discord";
import { getVipPriceIdr } from "@/lib/billing";
import { FEATURE_LIMITS, type FeatureCode } from "@/lib/premium";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.pricing.metaTitle} | Finch Dashboard` };
}

/** Format harga mengikuti pola BillingPanel: Intl sesuai bahasa aktif. */
function formatHarga(amount: number, locale: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} IDR`;
  }
}

/**
 * Halaman publik Harga: kartu Free vs VIP, tabel batas fitur dari katalog
 * FEATURE_LIMITS, dan seksi kedaluwarsa + refund. Harga VIP hanya dari
 * getVipPriceIdr() (env server); bila null, tampilkan teks harga tidak
 * tersedia tanpa angka karangan. Tanpa testimoni/diskon/statistik fiktif.
 */
export default async function PricingPage() {
  await connection();
  const lang = await getLang();
  const dict = getDict(lang);
  const p = dict.pricing;
  const l = dict.landing;
  const locale = lang === "en" ? "en-US" : "id-ID";

  let priceIdr: number | null = null;
  try {
    priceIdr = getVipPriceIdr();
  } catch {
    priceIdr = null;
  }

  const featureCodes = Object.keys(FEATURE_LIMITS) as FeatureCode[];

  const primaryBtnCls =
    "inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";
  const ghostBtnCls =
    "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-5 text-sm font-medium text-fg hover:border-brand hover:text-brand focus-visible:outline-2 focus-visible:outline-brand";

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto w-full max-w-6xl px-4 py-12 sm:py-16">
        <h1 className="text-3xl font-bold tracking-tight text-fg sm:text-4xl">{p.title}</h1>
        <p className="mt-3 max-w-2xl text-sm leading-relaxed text-muted sm:text-base">
          {p.subtitle}
        </p>

        {/* Kartu Free vs VIP */}
        <div className="mt-10 grid gap-6 md:grid-cols-2">
          <section
            aria-label={p.freeName}
            className="flex flex-col rounded-2xl border border-edge bg-panel p-6 sm:p-8"
          >
            <h2 className="text-lg font-bold text-fg">{p.freeName}</h2>
            <p className="mt-4 text-3xl font-extrabold tracking-tight text-fg">{p.freePrice}</p>
            <p className="mt-3 flex-1 text-sm leading-relaxed text-muted">{p.freeDesc}</p>
            <div className="mt-6">
              <Link href="/dashboard" className={ghostBtnCls}>
                {p.ctaFree}
              </Link>
            </div>
          </section>

          <section
            aria-label={p.vipName}
            className="flex flex-col rounded-2xl border border-brand bg-panel p-6 sm:p-8"
          >
            <h2 className="text-lg font-bold text-fg">{p.vipName}</h2>
            {priceIdr !== null ? (
              <>
                <p className="mt-4 text-3xl font-extrabold tracking-tight text-fg">
                  {formatHarga(priceIdr, locale)}
                </p>
                <p className="mt-1 text-sm text-muted">
                  {p.perThirtyDays} · {p.perServer}
                </p>
              </>
            ) : (
              <p className="mt-4 text-lg font-semibold text-fg">{dict.billing.priceUnavailable}</p>
            )}
            <p className="mt-3 flex-1 text-sm leading-relaxed text-muted">{p.vipDesc}</p>
            <div className="mt-6">
              <Link href="/dashboard" className={primaryBtnCls}>
                {p.ctaVip}
              </Link>
              <p className="mt-2 text-xs leading-relaxed text-muted">{p.ctaVipNote}</p>
            </div>
          </section>
        </div>

        {/* Tabel batas fitur dari katalog nyata */}
        <section aria-label={p.limitsTitle} className="mt-12">
          <h2 className="text-xl font-bold tracking-tight text-fg">{p.limitsTitle}</h2>
          <div className="mt-4 overflow-x-auto rounded-xl border border-edge bg-panel">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
                  <th scope="col" className="px-4 py-2.5 font-medium">{p.colFeature}</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">{p.colFree}</th>
                  <th scope="col" className="px-4 py-2.5 text-right font-medium">{p.colVip}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {featureCodes.map((code) => (
                  <tr key={code}>
                    <td className="px-4 py-2.5 text-fg">{p.features[code]}</td>
                    <td className="px-4 py-2.5 text-right text-muted">{FEATURE_LIMITS[code].free}</td>
                    <td className="px-4 py-2.5 text-right font-semibold text-brand">
                      {FEATURE_LIMITS[code].vip}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs leading-relaxed text-muted">{p.noteBody}</p>
        </section>

        {/* Kedaluwarsa & refund */}
        <div className="mt-12 grid gap-6 md:grid-cols-2">
          <section aria-label={p.expiryTitle} className="rounded-2xl border border-edge bg-panel p-6">
            <h2 className="text-base font-bold text-fg">{p.expiryTitle}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{p.expiryBody}</p>
          </section>
          <section aria-label={p.refundTitle} className="rounded-2xl border border-edge bg-panel p-6">
            <h2 className="text-base font-bold text-fg">{p.refundTitle}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{p.refundBody}</p>
            <p className="mt-3 flex flex-wrap gap-4 text-sm">
              <Link
                href="/terms"
                className="inline-flex min-h-[44px] items-center font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
              >
                {p.termsLink}
              </Link>
              <Link
                href="/privacy"
                className="inline-flex min-h-[44px] items-center font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
              >
                {p.privacyLink}
              </Link>
            </p>
          </section>
        </div>
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
              {dict.nav.pricing}
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
