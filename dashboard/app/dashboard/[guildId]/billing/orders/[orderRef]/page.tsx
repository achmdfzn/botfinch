import { notFound } from "next/navigation";
import { connection } from "next/server";
import type { Metadata } from "next";
import SiteHeader from "@/components/SiteHeader";
import EmptyState from "@/components/EmptyState";
import GuildErrorState from "@/components/GuildErrorState";
import ReloadButton from "@/components/ReloadButton";
import PageHeader from "@/components/PageHeader";
import OrderStatusPoller, {
  type OrderDetailView,
} from "@/components/OrderStatusPoller";
import { getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";
import { fetchUserGuilds } from "@/lib/access";
import { dbConfigured, getBillingOrderByRef } from "@/lib/db";
import { getDict, getLang } from "@/lib/i18n";

export const instant = false;

export async function generateMetadata(): Promise<Metadata> {
  const dict = getDict(await getLang());
  return { title: `${dict.billing.orderDetail.metaTitle} | Finch Dashboard` };
}

/**
 * Halaman status satu pesanan billing. Pola akses mengikuti halaman guild
 * lain. Pesanan wajib milik guild pada URL: getBillingOrderByRef yang
 * hasilnya guild_id berbeda (atau pesanan tidak ada) dijawab notFound().
 * Ringkasan awal dirender server dari baris DB, lalu OrderStatusPoller
 * (client) memperbarui status lewat API detail selama belum terminal.
 */
export default async function GuildBillingOrderPage({
  params,
}: {
  params: Promise<{ guildId: string; orderRef: string }>;
}) {
  await connection();
  const { guildId, orderRef } = await params;
  const lang = await getLang();
  const dict = getDict(lang);
  const gc = dict.guild.common;
  const b = dict.billing;
  const od = b.orderDetail;
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

  let order: Awaited<ReturnType<typeof getBillingOrderByRef>> = null;
  try {
    order = await getBillingOrderByRef(orderRef);
  } catch {
    order = null;
  }
  if (!order || order.guild_id !== guildId) notFound();

  const initialOrder: OrderDetailView = {
    order_ref: order.order_ref,
    plan_id: order.plan_id,
    amount_idr: order.amount_idr,
    currency: order.currency,
    status: order.status,
    provider: order.provider,
    provider_redirect_url: order.provider_redirect_url,
    created_at: order.created_at,
    expires_at: order.expires_at,
    paid_at: order.paid_at,
    entitlement_applied_at: order.entitlement_applied_at,
  };

  return (
    <div className="w-full">
      <PageHeader title={od.title} description={od.subtitle} />
      <OrderStatusPoller
        guildId={guildId}
        orderRef={orderRef}
        initialStatus={order.status}
        initialOrder={initialOrder}
        dict={dict}
        lang={lang}
      />
    </div>
  );
}
