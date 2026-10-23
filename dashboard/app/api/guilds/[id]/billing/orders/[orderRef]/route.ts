import { NextResponse } from "next/server";
import {
  getBillingOrderByRef,
  touchBillingOrderReconcile,
  withDbError,
  type BillingOrder,
} from "@/lib/db";
import { requireManager } from "@/lib/access";
import { getProviderById } from "@/lib/payments";
import { processProviderStatus } from "@/lib/payments/service";

const RECONCILE_AFTER_MS = 30_000;

/**
 * Detail satu order (manager). Anti-IDOR: order dari guild lain dijawab
 * 404 sama seperti order yang tidak ada.
 * Rekonsiliasi malas: order created/pending yang datanya basi (>30 detik)
 * dicek langsung ke provider dan diproses lewat jalur tunggal service —
 * menutup celah webhook yang hilang/terlambat tanpa cron. Order 'paid'
 * yang penerapan entitlement-nya terputus (entitlement_applied_at NULL)
 * juga direkonsiliasi agar jalur pemulihan service bisa berjalan dari
 * halaman ini. Percobaan rekonsiliasi dicatat via
 * touchBillingOrderReconcile SEBELUM memanggil provider, agar throttle
 * 30 detik menahan panggilan berulang walau status tidak berubah.
 */
async function getImpl(
  _req: Request,
  { params }: { params: Promise<{ id: string; orderRef: string }> },
) {
  const { id, orderRef } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  let order: BillingOrder | null = await getBillingOrderByRef(orderRef);
  if (!order || order.guild_id !== id) {
    return NextResponse.json({ error: "order_not_found" }, { status: 404 });
  }

  const stale =
    order.updated_at !== null &&
    Date.now() - new Date(order.updated_at).getTime() > RECONCILE_AFTER_MS;
  const needsReconcile =
    order.status === "created" ||
    order.status === "pending" ||
    (order.status === "paid" && order.entitlement_applied_at === null);
  if (needsReconcile && stale) {
    const provider = getProviderById(order.provider);
    if (provider) {
      await touchBillingOrderReconcile(orderRef);
      try {
        const st = await provider.fetchStatus(
          order.order_ref,
          order.provider_txn_id ?? undefined,
        );
        await processProviderStatus(order, st, { source: "reconcile" });
        const fresh = await getBillingOrderByRef(orderRef);
        if (fresh && fresh.guild_id === id) order = fresh;
      } catch {
        // Rekonsiliasi best-effort: kegagalan provider tidak boleh
        // menggagalkan tampilan detail — tampilkan data terakhir.
      }
    }
  }

  return NextResponse.json({
    order: {
      order_ref: order.order_ref,
      guild_id: order.guild_id,
      plan_id: order.plan_id,
      amount_idr: order.amount_idr,
      currency: order.currency,
      duration_days: order.duration_days,
      status: order.status,
      provider: order.provider,
      redirect_url: order.provider_redirect_url,
      created_at: order.created_at,
      expires_at: order.expires_at,
      paid_at: order.paid_at,
      entitlement_applied_at: order.entitlement_applied_at,
      updated_at: order.updated_at,
    },
  });
}

export const GET = withDbError(getImpl);
