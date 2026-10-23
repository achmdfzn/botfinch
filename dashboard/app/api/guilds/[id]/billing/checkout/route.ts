import { NextResponse } from "next/server";
import {
  createBillingOrder,
  dbConfigured,
  expireStaleBillingOrders,
  findActiveBillingOrder,
  setBillingOrderProviderInfo,
  transitionBillingOrder,
  withDbError,
} from "@/lib/db";
import { getSessionDiscordId, requireManager } from "@/lib/access";
import {
  getActiveProviderId,
  getPlan,
  getVip30dPriceIdr,
  isBillingConfigured,
} from "@/lib/billing";
import { getActiveProvider } from "@/lib/payments";
import { parseJsonBody } from "@/lib/validate";

/**
 * Buat order billing + checkout provider (manager guild).
 * Harga SELALU dari env server (getVip30dPriceIdr) — field harga/tier apa
 * pun di body diabaikan total. Order aktif (created/pending) yang sudah
 * ada dipakai ulang agar dobel-klik tidak membuat dua tagihan.
 */
async function postImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  if (!isBillingConfigured()) {
    return NextResponse.json({ error: "billing_not_configured" }, { status: 503 });
  }
  const buyer = await getSessionDiscordId();
  if (!buyer) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const plan = getPlan(body.plan_id);
  if (!plan) {
    return NextResponse.json({ error: "unknown_plan" }, { status: 400 });
  }
  const priceIdr = getVip30dPriceIdr();
  const providerId = getActiveProviderId();
  const provider = getActiveProvider();
  if (priceIdr === null || !providerId || !provider) {
    return NextResponse.json({ error: "billing_not_configured" }, { status: 503 });
  }

  // Order basi (lewat expires_at, status belum berubah) ditutup dulu:
  // indeks unik order-aktif melihat status, bukan waktu.
  await expireStaleBillingOrders(id, plan.id);

  const existing = await findActiveBillingOrder(id, plan.id);
  if (existing && existing.provider_redirect_url) {
    return NextResponse.json({
      order_ref: existing.order_ref,
      redirect_url: existing.provider_redirect_url,
      status: existing.status,
      reused: true,
    });
  }
  if (existing) {
    // Order aktif menggantung TANPA tautan bayar (proses mati di antara
    // pembuatan order dan penyimpanan info provider): tutup sebagai
    // failed agar pembeli tidak terjebak pada order yang tak bisa
    // dibayar, lalu buat order baru di bawah.
    await transitionBillingOrder(existing.order_ref, "failed", ["created", "pending"]);
  }

  const orderRef = `FINCH-${id}-${Date.now().toString(36).toUpperCase()}-${crypto
    .randomUUID()
    .slice(0, 8)
    .toUpperCase()}`;
  const expiresAt = new Date(Date.now() + 60 * 60 * 1000).toISOString();
  try {
    await createBillingOrder({
      orderRef,
      buyerUserId: buyer,
      guildId: id,
      planId: plan.id,
      amountIdr: priceIdr,
      currency: plan.currency,
      durationDays: plan.durationDays,
      provider: providerId,
      expiresAt,
    });
  } catch (e) {
    // Balapan dua POST bersamaan: indeks unik parsial
    // idx_billing_orders_one_active (satu order aktif per guild+plan)
    // menolak insert kedua. Pemenangnya sudah punya order aktif —
    // kembalikan order itu sebagai reused alih-alih 500.
    const err = e as { code?: unknown; message?: unknown };
    const isUniqueViolation =
      err?.code === "23505" ||
      (typeof err?.message === "string" &&
        /duplicate key|unique constraint|idx_billing_orders_one_active/i.test(err.message));
    if (!isUniqueViolation) throw e;
    const winner = await findActiveBillingOrder(id, plan.id);
    if (!winner) throw e;
    return NextResponse.json({
      order_ref: winner.order_ref,
      redirect_url: winner.provider_redirect_url,
      status: winner.status,
      reused: true,
    });
  }

  const appBase = (process.env.APP_BASE_URL ?? "").replace(/\/+$/, "");
  const origin = appBase || new URL(req.url).origin;
  const detailUrl = `${origin}/dashboard/${id}/billing/orders/${orderRef}`;

  let checkout: { providerTxnId: string; redirectUrl: string };
  try {
    checkout = await provider.createCheckout({
      orderRef,
      amountIdr: priceIdr,
      description: "Finch Premium VIP 30 hari",
      successRedirectUrl: detailUrl,
      failureRedirectUrl: detailUrl,
    });
  } catch {
    // Gagal di provider: tutup order sebagai failed agar tidak menggantung,
    // dan jawab generik — detail error internal tidak bocor ke client.
    await transitionBillingOrder(orderRef, "failed", ["created"]);
    return NextResponse.json({ error: "provider_error" }, { status: 502 });
  }
  await setBillingOrderProviderInfo(orderRef, checkout.providerTxnId, checkout.redirectUrl);
  return NextResponse.json({
    order_ref: orderRef,
    redirect_url: checkout.redirectUrl,
  });
}

export const POST = withDbError(postImpl);
