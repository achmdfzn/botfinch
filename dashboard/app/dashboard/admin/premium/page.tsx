import type { Metadata } from "next";
import Link from "next/link";
import { connection } from "next/server";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import PageHeader from "@/components/PageHeader";
import AdminPremium from "@/components/AdminPremium";
import { SignInButton } from "@/components/AuthButtons";
import { getSessionDiscordId, getSessionSafe, requireBotOwner } from "@/lib/access";
import { getDict, getLang } from "@/lib/i18n";

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.premium.admin.metaTitle} | Finch Dashboard` };
}

/**
 * Panel admin Premium: segment statis di bawah /dashboard, BUKAN di bawah
 * [guildId], jadi halaman ini menjaga dirinya sendiri:
 * 1. Belum login (tidak ada sesi / Discord ID) -> keadaan "masuk dulu".
 * 2. Login tapi bukan owner bot (requireBotOwner non-null) -> akses ditolak,
 *    tanpa menampilkan data entitlement apa pun.
 * 3. Lolos -> <AdminPremium> (client) yang mengambil data lewat
 *    GET /api/admin/entitlements.
 */
export default async function AdminPremiumPage() {
  await connection(); // halaman dinamis: sesi + guard owner, jangan di-prerender
  const lang = await getLang();
  const dict = getDict(lang);
  const a = dict.premium.admin;
  const d = dict.dashboard;

  const backLink = (
    <Link
      href="/dashboard"
      className="mb-4 inline-flex min-h-[44px] items-center text-sm text-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-brand"
    >
      {dict.nav.back}
    </Link>
  );

  const session = await getSessionSafe();
  const discordId = session ? await getSessionDiscordId() : null;
  if (!session || !discordId) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={d.signinTitle} body={d.signinBody} action={<SignInButton />} />
        </main>
      </div>
    );
  }

  const denied = await requireBotOwner();
  if (denied) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          {backLink}
          <EmptyState title={a.deniedTitle} body={a.deniedBody} />
        </main>
      </div>
    );
  }

  return (
    <div>
      <SiteHeader />
      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        {backLink}
        <PageHeader title={a.title} description={a.subtitle} />
        <AdminPremium dict={dict} lang={lang} />
      </main>
    </div>
  );
}
