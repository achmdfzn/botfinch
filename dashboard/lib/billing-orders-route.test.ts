/**
 * Route GET billing orders (list + detail):
 * - list: hanya field aman (tanpa buyer_user_id / provider_txn_id).
 * - detail anti-IDOR: order guild lain -> 404 sama seperti tak ada.
 * - rekonsiliasi malas: order basi (>30 dtk) created/pending dicek ke
 *   provider; touch throttle dicatat SEBELUM fetch agar panggilan
 *   berulang tertahan walau status tak berubah. Order 'paid' yang
 *   penerapan entitlement-nya terputus (applied_at NULL) juga
 *   direkonsiliasi (pemicu jalur pemulihan service).
 * - order segar / paid yang sudah diterapkan: provider tidak dipanggil.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  withDbError: (fn: unknown) => fn,
  getBillingOrderByRef: vi.fn(),
  listBillingOrders: vi.fn(async () => []),
  touchBillingOrderReconcile: vi.fn(async () => undefined),
}));

vi.mock("@/lib/access", () => ({
  requireManager: vi.fn(async () => null),
}));

const fetchStatus = vi.fn(async () => ({
  kind: "paid",
  amountIdr: 50000,
  currency: "IDR",
  rawStatus: "settlement",
  providerTxnId: "txn-1",
}));
vi.mock("@/lib/payments", () => ({
  getProviderById: vi.fn(() => ({ id: "midtrans", fetchStatus })),
}));

vi.mock("@/lib/payments/service", () => ({
  processProviderStatus: vi.fn(async () => ({ outcome: "applied:activated" })),
}));

import * as db from "@/lib/db";
import * as access from "@/lib/access";
import * as service from "@/lib/payments/service";
import { GET as listGet } from "../app/api/guilds/[id]/billing/orders/route";
import { GET as detailGet } from "../app/api/guilds/[id]/billing/orders/[orderRef]/route";
import type { BillingOrder } from "@/lib/db";

const getOrder = vi.mocked(db.getBillingOrderByRef);
const listOrders = vi.mocked(db.listBillingOrders);
const touch = vi.mocked(db.touchBillingOrderReconcile);
const manager = vi.mocked(access.requireManager);
const processStatus = vi.mocked(service.processProviderStatus);

const GUILD = "111111111111111111";
const REF = "FINCH-111111111111111111-M3ABCDEF-ABCD1234";
const listCtx = { params: Promise.resolve({ id: GUILD }) };
const detailCtx = { params: Promise.resolve({ id: GUILD, orderRef: REF }) };
const req = () => new Request("http://localhost/api/guilds/x/billing/orders");

function orderFixture(overrides: Partial<BillingOrder> = {}): BillingOrder {
  return {
    id: 1,
    order_ref: REF,
    buyer_user_id: "333333333333333333",
    guild_id: GUILD,
    plan_id: "vip_monthly",
    amount_idr: 50000,
    currency: "IDR",
    duration_days: 30,
    status: "pending",
    provider: "midtrans",
    provider_txn_id: "txn-1",
    provider_redirect_url: "https://example.com/pay",
    created_at: "2026-10-23T00:00:00.000Z",
    expires_at: "2026-10-23T01:00:00.000Z",
    paid_at: null,
    entitlement_applied_at: null,
    updated_at: new Date().toISOString(),
    ...overrides,
  };
}

const stale = (seconds: number) =>
  new Date(Date.now() - seconds * 1000).toISOString();

beforeEach(() => {
  vi.clearAllMocks();
  manager.mockResolvedValue(null);
  listOrders.mockResolvedValue([]);
  getOrder.mockResolvedValue(orderFixture());
  fetchStatus.mockResolvedValue({
    kind: "paid",
    amountIdr: 50000,
    currency: "IDR",
    rawStatus: "settlement",
    providerTxnId: "txn-1",
  } as never);
  processStatus.mockResolvedValue({ outcome: "applied:activated" });
});

describe("GET billing/orders (list)", () => {
  it("mengembalikan ringkasan aman tanpa buyer_user_id/provider_txn_id", async () => {
    listOrders.mockResolvedValue([orderFixture({ status: "paid" })]);
    const res = await listGet(req(), listCtx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { orders: Record<string, unknown>[] };
    expect(json.orders).toHaveLength(1);
    expect(json.orders[0].order_ref).toBe(REF);
    expect(json.orders[0].status).toBe("paid");
    expect(json.orders[0]).not.toHaveProperty("buyer_user_id");
    expect(json.orders[0]).not.toHaveProperty("provider_txn_id");
    expect(listOrders).toHaveBeenCalledWith(GUILD, 20);
  });

  it("(d) order lama plan_id vip_30d tetap terbaca apa adanya di list", async () => {
    listOrders.mockResolvedValue([orderFixture({ status: "paid", plan_id: "vip_30d" })]);
    const res = await listGet(req(), listCtx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { orders: Record<string, unknown>[] };
    expect(json.orders).toHaveLength(1);
    expect(json.orders[0].plan_id).toBe("vip_30d");
    expect(json.orders[0].status).toBe("paid");
  });

  it("(d2) detail order lama plan_id vip_30d tetap terbaca (bukan 404)", async () => {
    getOrder.mockResolvedValue(
      orderFixture({ status: "paid", plan_id: "vip_30d", entitlement_applied_at: stale(3500) }),
    );
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order: { plan_id: string; status: string } };
    expect(json.order.plan_id).toBe("vip_30d");
    expect(json.order.status).toBe("paid");
  });
});

describe("GET billing/orders/[orderRef] (detail)", () => {
  it("order guild lain -> 404 (anti-IDOR), provider tidak dipanggil", async () => {
    getOrder.mockResolvedValue(orderFixture({ guild_id: "999999999999999999" }));
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(404);
    expect(fetchStatus).not.toHaveBeenCalled();
    expect(touch).not.toHaveBeenCalled();
  });

  it("order tidak ada -> 404", async () => {
    getOrder.mockResolvedValue(null);
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(404);
  });

  it("order pending segar -> tanpa rekonsiliasi", async () => {
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order: { status: string } };
    expect(json.order.status).toBe("pending");
    expect(fetchStatus).not.toHaveBeenCalled();
    expect(touch).not.toHaveBeenCalled();
  });

  it("order pending basi -> touch dulu, lalu fetchStatus + proses, respons = status segar", async () => {
    getOrder
      .mockResolvedValueOnce(orderFixture({ updated_at: stale(120) }))
      .mockResolvedValue(
        orderFixture({ status: "paid", paid_at: new Date().toISOString() }),
      );
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order: { status: string } };
    expect(json.order.status).toBe("paid");
    expect(touch).toHaveBeenCalledWith(REF);
    expect(fetchStatus).toHaveBeenCalledTimes(1);
    // Urutan: touch (throttle) SEBELUM panggilan provider.
    expect(touch.mock.invocationCallOrder[0]).toBeLessThan(
      fetchStatus.mock.invocationCallOrder[0],
    );
    expect(processStatus).toHaveBeenCalledWith(
      expect.objectContaining({ order_ref: REF }),
      expect.objectContaining({ kind: "paid" }),
      { source: "reconcile" },
    );
  });

  it("order paid basi TANPA penanda penerapan -> direkonsiliasi (pemicu pemulihan)", async () => {
    getOrder.mockResolvedValue(
      orderFixture({
        status: "paid",
        paid_at: stale(3600),
        entitlement_applied_at: null,
        updated_at: stale(3600),
      }),
    );
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(200);
    expect(fetchStatus).toHaveBeenCalledTimes(1);
    expect(processStatus).toHaveBeenCalled();
  });

  it("order paid yang sudah diterapkan -> provider tidak dipanggil lagi", async () => {
    getOrder.mockResolvedValue(
      orderFixture({
        status: "paid",
        paid_at: stale(3600),
        entitlement_applied_at: stale(3500),
        updated_at: stale(3600),
      }),
    );
    const res = await detailGet(req(), detailCtx);
    expect(res.status).toBe(200);
    expect(fetchStatus).not.toHaveBeenCalled();
  });
});
