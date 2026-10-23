import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import GuildErrorState from "@/components/GuildErrorState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import BillingPanel, {
  type BillingOrderSummary,
  type BillingUsageRow,
} from "@/components/BillingPanel";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import {
  countAutoResponses,
  countEnabledAnnouncements,
  countGiveawayRequestsPending,
  countSelfRolePanels,
  dbConfigured,
  getEntitlement,
  listBillingOrders,
} from "@/lib/db";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";
import {
  getActiveProviderId,
  getVipPriceIdr,
  isBillingConfigured,
} from "@/lib/billing";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.billing.metaTitle} | Finch Dashboard` };
}

/**
 * Halaman billing per server: status paket, pembelian VIP 30 hari, dan
 * riwayat pesanan. Pola akses (sesi, izin Kelola Server, dbConfigured)
 * mengikuti persis halaman guild lain. Kegagalan baca entitlement, harga,
 * atau daftar pesanan tidak merusak halaman: nilai aman dipakai dan panel
 * tetap tampil dengan status jujur.
 */
export default async function GuildBillingPage({
  params,
}: {
  params: Promise<{ guildId: string }>;
}) {
  await connection();
  const { guildId } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const b = dict.billing;
  const session = await getSessionSafe();
  if (!session?.accessToken) {
    return (
      <div>
        <SiteHeader />
        <main className="mx-auto max-w-3xl px-4 py-16">
          <EmptyState title={gc.signinTitle} body={b.signinBody} />
        </main>
      </div>
    );
  }

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
    return <GuildErrorState title={gc.dbTitle} body={b.dbBody} />;
  }

  let entitlement: Awaited<ReturnType<typeof getEntitlement>> = null;
  try {
    entitlement = await getEntitlement(guildId);
  } catch {
    entitlement = null;
  }
  const tier = getEffectiveTierFromRow(entitlement);

  let billingConfigured = false;
  try {
    billingConfigured = isBillingConfigured();
  } catch {
    billingConfigured = false;
  }

  let priceIdr: number | null = null;
  try {
    priceIdr = getVipPriceIdr();
  } catch {
    priceIdr = null;
  }

  let providerId: string | null = null;
  try {
    providerId = getActiveProviderId();
  } catch {
    providerId = null;
  }

  // Pemakaian kuota: HANYA dari data yang disimpan dashboard untuk guild
  // ini, dihitung dengan fungsi COUNT yang sama dengan yang dipakai
  // gate di route API (bukan diturunkan dari daftar ber-LIMIT, agar
  // angka tampilan tidak bisa lebih kecil dari angka gate).
  // custom_commands tidak ditampilkan (dashboard tidak punya datanya)
  // dan giveaway yang sedang berjalan adalah data bot, jadi untuk
  // giveaway yang dihitung hanya request berstatus pending milik
  // dashboard.
  let usage: BillingUsageRow[] = [];
  try {
    const [announcementsUsed, selfRolePanelsUsed, autoResponsesUsed, giveawayPending] =
      await Promise.all([
        countEnabledAnnouncements(guildId),
        countSelfRolePanels(guildId),
        countAutoResponses(guildId),
        countGiveawayRequestsPending(guildId),
      ]);
    usage = [
      {
        feature: "autoresponders",
        used: autoResponsesUsed,
        limit: FEATURE_LIMITS.autoresponders[tier],
      },
      {
        feature: "giveaways_active",
        used: giveawayPending,
        limit: FEATURE_LIMITS.giveaways_active[tier],
        pendingCount: giveawayPending,
      },
      {
        feature: "selfrole_panels",
        used: selfRolePanelsUsed,
        limit: FEATURE_LIMITS.selfrole_panels[tier],
      },
      {
        feature: "announcements_active",
        used: announcementsUsed,
        limit: FEATURE_LIMITS.announcements_active[tier],
      },
    ];
  } catch {
    usage = [];
  }

  let orders: BillingOrderSummary[] = [];
  try {
    const rows = await listBillingOrders(guildId, 10);
    orders = rows.map((o) => ({
      order_ref: o.order_ref,
      plan_id: o.plan_id,
      amount_idr: o.amount_idr,
      currency: o.currency,
      status: o.status,
      provider_redirect_url: o.provider_redirect_url,
      created_at: o.created_at,
      expires_at: o.expires_at,
    }));
  } catch {
    orders = [];
  }

  return (
    <div className="w-full">
      <PageHeader title={b.title} description={b.subtitle} />
      <BillingPanel
        guildId={guildId}
        tier={tier}
        entitlementStatus={entitlement?.status ?? null}
        entitlementExpiresAt={entitlement?.expires_at ?? null}
        billingConfigured={billingConfigured}
        priceIdr={priceIdr}
        providerId={providerId}
        orders={orders}
        usage={usage}
        dict={dict}
        lang={lang}
      />
    </div>
  );
}
