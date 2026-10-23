import { connection } from "next/server";
import type { Metadata } from "next";
import Link from "next/link";
import SiteHeader from "@/components/SiteHeader";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.terms.metaTitle} | Finch Dashboard` };
}

/**
 * Halaman publik Syarat Layanan. Isi faktual dari perilaku produk
 * (VIP per server, 30 hari, hosted checkout, aktivasi terverifikasi,
 * refund, harga) dan seluruh teksnya berasal dari kamus terms.
 */
export default async function TermsPage() {
  await connection();
  const dict = getDict(await getLang());
  const t = dict.terms;
  const l = dict.landing;

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-3xl px-4 py-12">
        <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">{t.title}</h1>
        <p className="mt-2 text-sm text-muted">{t.lastUpdated}</p>
        <p className="mt-4 text-sm leading-relaxed text-muted sm:text-base">{t.intro}</p>
        <div className="mt-8 space-y-8">
          {t.sections.map((s) => (
            <section key={s.heading} aria-label={s.heading}>
              <h2 className="text-base font-semibold text-fg sm:text-lg">{s.heading}</h2>
              <p className="mt-2 text-sm leading-relaxed text-muted sm:text-base">{s.body}</p>
            </section>
          ))}
        </div>
        <div className="mt-10 border-t border-edge pt-6">
          <Link
            href="/"
            className="inline-flex min-h-[44px] items-center text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
          >
            {t.backHome}
          </Link>
        </div>
      </main>
      <footer className="border-t border-edge">
        <div className="mx-auto max-w-3xl px-4 py-6 text-sm text-muted">
          <p>{l.footerTagline}</p>
          <p className="mt-1 text-xs">{l.footerRights}</p>
        </div>
      </footer>
    </div>
  );
}
