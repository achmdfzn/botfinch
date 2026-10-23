import { NextResponse } from "next/server";
import { listBillingOrders, withDbError, type BillingOrder } from "@/lib/db";
import { requireManager } from "@/lib/access";

/** Field order yang aman ditampilkan ke manager (tanpa ID internal provider/pembeli). */
function safeOrderSummary(order: BillingOrder) {
  return {
    order_ref: order.order_ref,
    plan_id: order.plan_id,
    amount_idr: order.amount_idr,
    currency: order.currency,
    duration_days: order.duration_days,
    status: order.status,
    provider: order.provider,
    created_at: order.created_at,
    expires_at: order.expires_at,
    paid_at: order.paid_at,
  };
}

/** Daftar order billing terakhir guild (manager). */
async function getImpl(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const orders = await listBillingOrders(id, 20);
  return NextResponse.json({ orders: orders.map(safeOrderSummary) });
}

export const GET = withDbError(getImpl);
