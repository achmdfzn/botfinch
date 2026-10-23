/**
 * Unit billing & payments:
 * - parser harga env ketat (digit murni > 0) & state machine order.
 * - mapping status Midtrans (capture challenge = pending, BUKAN paid;
 *   partial_refund = unknown) & Xendit (PAID/SETTLED/EXPIRED).
 * - service processProviderStatus: klaim atomik menentukan idempotensi —
 *   apply hanya dipanggil pemenang klaim; nominal/currency beda ditolak
 *   tanpa klaim; settlement setelah terminal diabaikan.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  withDbError: (fn: unknown) => fn,
  createBillingOrder: vi.fn(),
  getBillingOrderByRef: vi.fn(),
  findActiveBillingOrder: vi.fn(),
  listBillingOrders: vi.fn(async () => []),
  setBillingOrderProviderInfo: vi.fn(async () => undefined),
  transitionBillingOrder: vi.fn(async () => true),
  recordWebhookEvent: vi.fn(async () => true),
  claimBillingOrderPaid: vi.fn(async () => null),
  applyPaymentToEntitlement: vi.fn(async () => "activated"),
  revokeEntitlementForRefund: vi.fn(async () => true),
  markBillingOrderApplied: vi.fn(async () => true),
  getEntitlement: vi.fn(async () => null),
}));

import * as db from "@/lib/db";
import {
  canTransitionOrder,
  getActiveProviderId,
  getPlan,
  getVip30dPriceIdr,
  isBillingConfigured,
  transitionSources,
} from "@/lib/billing";
import { mapMidtransStatus, parseMidtransGrossAmount } from "@/lib/payments/midtrans";
import { mapXenditStatus } from "@/lib/payments/xendit";
import { processProviderStatus } from "@/lib/payments/service";
import type { BillingOrder } from "@/lib/db";

const claim = vi.mocked(db.claimBillingOrderPaid);
const apply = vi.mocked(db.applyPaymentToEntitlement);
const transition = vi.mocked(db.transitionBillingOrder);
const revoke = vi.mocked(db.revokeEntitlementForRefund);
const mark = vi.mocked(db.markBillingOrderApplied);
const getOrder = vi.mocked(db.getBillingOrderByRef);
const getEnt = vi.mocked(db.getEntitlement);

const ENV_KEYS = [
  "BILLING_VIP_30D_PRICE_IDR",
  "PAYMENT_PROVIDER",
  "MIDTRANS_SERVER_KEY",
  "MIDTRANS_CLIENT_KEY",
  "XENDIT_SECRET_KEY",
  "XENDIT_CALLBACK_TOKEN",
] as const;
const savedEnv: Record<string, string | undefined> = {};
for (const k of ENV_KEYS) savedEnv[k] = process.env[k];

function orderFixture(overrides: Partial<BillingOrder> = {}): BillingOrder {
  return {
    id: 1,
    order_ref: "FINCH-111-M3ABCDEF-ABCD1234",
    buyer_user_id: "333333333333333333",
    guild_id: "111111111111111111",
    plan_id: "vip_30d",
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
    updated_at: "2026-10-23T00:00:00.000Z",
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  for (const k of ENV_KEYS) delete process.env[k];
  claim.mockResolvedValue(null);
  apply.mockResolvedValue("activated");
  transition.mockResolvedValue(true);
  revoke.mockResolvedValue(true);
  mark.mockResolvedValue(true);
  getOrder.mockResolvedValue(null);
  getEnt.mockResolvedValue(null);
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
});

describe("getVip30dPriceIdr — parser harga ketat", () => {
  it("digit murni > 0 diterima", () => {
    process.env.BILLING_VIP_30D_PRICE_IDR = "50000";
    expect(getVip30dPriceIdr()).toBe(50000);
  });
  it("selain digit murni ditolak (null)", () => {
    for (const bad of ["", "0", "-5", "50.000", "50000.00", "abc", " 50000", "50000 ", "5e4"]) {
      process.env.BILLING_VIP_30D_PRICE_IDR = bad;
      expect(getVip30dPriceIdr()).toBeNull();
    }
    delete process.env.BILLING_VIP_30D_PRICE_IDR;
    expect(getVip30dPriceIdr()).toBeNull();
  });
});

describe("getPlan / getActiveProviderId / isBillingConfigured", () => {
  it("plan hanya vip_30d", () => {
    expect(getPlan("vip_30d")).toEqual({ id: "vip_30d", durationDays: 30, currency: "IDR" });
    expect(getPlan("vip_365d")).toBeNull();
    expect(getPlan(undefined)).toBeNull();
  });
  it("provider hanya midtrans/xendit", () => {
    process.env.PAYMENT_PROVIDER = "midtrans";
    expect(getActiveProviderId()).toBe("midtrans");
    process.env.PAYMENT_PROVIDER = "stripe";
    expect(getActiveProviderId()).toBeNull();
    delete process.env.PAYMENT_PROVIDER;
    expect(getActiveProviderId()).toBeNull();
  });
  it("konfigurasi lengkap midtrans / xendit", () => {
    process.env.BILLING_VIP_30D_PRICE_IDR = "50000";
    process.env.PAYMENT_PROVIDER = "midtrans";
    expect(isBillingConfigured()).toBe(false);
    process.env.MIDTRANS_SERVER_KEY = "sk-test";
    expect(isBillingConfigured()).toBe(true);
    process.env.PAYMENT_PROVIDER = "xendit";
    expect(isBillingConfigured()).toBe(false);
    process.env.XENDIT_SECRET_KEY = "xnd-test";
    expect(isBillingConfigured()).toBe(false); // callback token belum ada
    process.env.XENDIT_CALLBACK_TOKEN = "tok-test";
    expect(isBillingConfigured()).toBe(true);
  });
});

describe("canTransitionOrder — state machine", () => {
  it("transisi sah", () => {
    expect(canTransitionOrder("created", "pending")).toBe(true);
    expect(canTransitionOrder("created", "paid")).toBe(true);
    expect(canTransitionOrder("pending", "paid")).toBe(true);
    expect(canTransitionOrder("pending", "expired")).toBe(true);
    expect(canTransitionOrder("expired", "paid")).toBe(true); // late settlement
    expect(canTransitionOrder("paid", "refunded")).toBe(true);
    expect(canTransitionOrder("paid", "disputed")).toBe(true);
  });
  it("transisi tidak sah", () => {
    expect(canTransitionOrder("paid", "paid")).toBe(false);
    expect(canTransitionOrder("failed", "paid")).toBe(false);
    expect(canTransitionOrder("cancelled", "paid")).toBe(false);
    expect(canTransitionOrder("refunded", "paid")).toBe(false);
    expect(canTransitionOrder("disputed", "paid")).toBe(false);
    expect(canTransitionOrder("created", "refunded")).toBe(false);
    expect(canTransitionOrder("pending", "pending")).toBe(false);
    expect(canTransitionOrder("aneh", "paid")).toBe(false);
  });
});

describe("Midtrans — parse amount & mapping status", () => {
  it("gross_amount pola resmi saja yang jadi integer", () => {
    expect(parseMidtransGrossAmount("50000.00")).toBe(50000);
    expect(parseMidtransGrossAmount("50000.50")).toBeUndefined();
    expect(parseMidtransGrossAmount("50000")).toBeUndefined();
    expect(parseMidtransGrossAmount(50000)).toBeUndefined();
    expect(parseMidtransGrossAmount("abc.00")).toBeUndefined();
  });
  it("settlement -> paid dengan nominal & currency", () => {
    const st = mapMidtransStatus({
      transaction_status: "settlement",
      gross_amount: "50000.00",
      currency: "IDR",
      transaction_id: "t-1",
    });
    expect(st).toMatchObject({ kind: "paid", amountIdr: 50000, currency: "IDR", providerTxnId: "t-1" });
  });
  it("capture challenge -> pending (BUKAN paid), deny -> failed, accept -> paid", () => {
    expect(mapMidtransStatus({ transaction_status: "capture", fraud_status: "challenge" }).kind).toBe("pending");
    expect(mapMidtransStatus({ transaction_status: "capture", fraud_status: "deny" }).kind).toBe("failed");
    expect(mapMidtransStatus({ transaction_status: "capture", fraud_status: "accept" }).kind).toBe("paid");
  });
  it("expire/deny/cancel/refund & partial_refund -> unknown", () => {
    expect(mapMidtransStatus({ transaction_status: "expire" }).kind).toBe("expired");
    expect(mapMidtransStatus({ transaction_status: "deny" }).kind).toBe("failed");
    expect(mapMidtransStatus({ transaction_status: "cancel" }).kind).toBe("cancelled");
    expect(mapMidtransStatus({ transaction_status: "refund" }).kind).toBe("refunded");
    const partial = mapMidtransStatus({ transaction_status: "partial_refund" });
    expect(partial.kind).toBe("unknown"); // hanya refund penuh yang mencabut
    expect(partial.rawStatus).toBe("partial_refund");
  });
});

describe("Xendit — mapping status", () => {
  it("PAID memakai paid_amount, SETTLED juga paid", () => {
    expect(mapXenditStatus({ status: "PAID", amount: 50000, paid_amount: 50000, currency: "IDR", id: "inv-1" }))
      .toMatchObject({ kind: "paid", amountIdr: 50000, currency: "IDR", providerTxnId: "inv-1" });
    expect(mapXenditStatus({ status: "SETTLED", amount: 50000 }).amountIdr).toBe(50000);
  });
  it("PENDING/EXPIRED/lainnya", () => {
    expect(mapXenditStatus({ status: "PENDING" }).kind).toBe("pending");
    expect(mapXenditStatus({ status: "EXPIRED" }).kind).toBe("expired");
    expect(mapXenditStatus({ status: "ANEH" }).kind).toBe("unknown");
  });
});

describe("transitionSources — sumber tunggal transisi (diturunkan dari ORDER_TRANSITIONS)", () => {
  it("konsisten dengan canTransitionOrder untuk semua pasangan", () => {
    const all = ["created", "pending", "paid", "failed", "expired", "cancelled", "refunded", "disputed"] as const;
    for (const to of all) {
      for (const from of all) {
        expect(transitionSources(to).includes(from)).toBe(canTransitionOrder(from, to));
      }
    }
    expect(transitionSources("refunded")).toEqual(["paid"]);
    expect(transitionSources("pending")).toEqual(["created"]);
  });
});

describe("processProviderStatus — jalur tunggal", () => {
  const paidStatus = { kind: "paid" as const, amountIdr: 50000, currency: "IDR", rawStatus: "settlement", providerTxnId: "txn-1" };

  it("paid + klaim menang -> apply sekali (activated)", async () => {
    const order = orderFixture();
    claim.mockResolvedValue({ order, previousStatus: "pending" });
    const res = await processProviderStatus(order, paidStatus, { source: "webhook" });
    expect(res.outcome).toBe("applied:activated");
    expect(claim).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(order.guild_id, 30, "midtrans", order.order_ref, undefined);
    // Penanda penerapan di-set setelah apply berhasil.
    expect(mark).toHaveBeenCalledWith(order.order_ref, "txn-1");
  });

  it("klaim kalah (event duplikat) -> already_applied, apply TIDAK dipanggil", async () => {
    claim.mockResolvedValue(null);
    const res = await processProviderStatus(orderFixture(), paidStatus, { source: "reconcile" });
    expect(res.outcome).toBe("already_applied");
    expect(apply).not.toHaveBeenCalled();
  });

  it("late settlement (previousStatus expired) -> note late_settlement", async () => {
    const order = orderFixture({ status: "expired" });
    claim.mockResolvedValue({ order, previousStatus: "expired" });
    const res = await processProviderStatus(order, paidStatus, { source: "webhook" });
    expect(res.outcome).toBe("applied:activated");
    expect(apply).toHaveBeenCalledWith(order.guild_id, 30, "midtrans", order.order_ref, "late_settlement");
  });

  it("nominal beda / hilang / currency beda -> amount_mismatch tanpa klaim", async () => {
    const order = orderFixture();
    for (const st of [
      { ...paidStatus, amountIdr: 60000 },
      { ...paidStatus, amountIdr: undefined },
      { ...paidStatus, currency: "USD" },
    ]) {
      const res = await processProviderStatus(order, st, { source: "webhook" });
      expect(res.outcome).toBe("amount_mismatch");
    }
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("settlement setelah failed/cancelled -> settlement_after_terminal tanpa klaim", async () => {
    for (const s of ["failed", "cancelled", "refunded", "disputed"]) {
      const res = await processProviderStatus(orderFixture({ status: s }), paidStatus, { source: "webhook" });
      expect(res.outcome).toBe("settlement_after_terminal");
    }
    expect(claim).not.toHaveBeenCalled();
  });

  it("pending hanya dari created; failed/expired transisi dari created/pending", async () => {
    const order = orderFixture({ status: "created" });
    expect((await processProviderStatus(order, { kind: "pending", rawStatus: "pending" }, { source: "webhook" })).outcome).toBe("pending");
    expect(transition).toHaveBeenCalledWith(order.order_ref, "pending", ["created"]);
    expect((await processProviderStatus(orderFixture(), { kind: "expired", rawStatus: "expire" }, { source: "webhook" })).outcome).toBe("transitioned");
    expect(transition).toHaveBeenCalledWith(orderFixture().order_ref, "expired", ["created", "pending"]);
    transition.mockResolvedValue(false);
    expect((await processProviderStatus(orderFixture(), { kind: "failed", rawStatus: "deny" }, { source: "webhook" })).outcome).toBe("ignored");
  });

  it("refund dari paid -> refunded + revoke; dari non-paid -> ignored tanpa revoke", async () => {
    const order = orderFixture({ status: "paid" });
    const res = await processProviderStatus(order, { kind: "refunded", rawStatus: "refund" }, { source: "webhook" });
    expect(res.outcome).toBe("refunded");
    expect(revoke).toHaveBeenCalledWith(order.guild_id, "midtrans", order.order_ref, 30);
    transition.mockResolvedValue(false);
    const res2 = await processProviderStatus(orderFixture(), { kind: "refunded", rawStatus: "refund" }, { source: "webhook" });
    expect(res2.outcome).toBe("ignored");
    expect(revoke).toHaveBeenCalledTimes(1);
  });

  it("disputed -> tandai saja, entitlement tidak diubah", async () => {
    const order = orderFixture({ status: "paid" });
    const res = await processProviderStatus(order, { kind: "disputed", rawStatus: "chargeback" }, { source: "webhook" });
    expect(res.outcome).toBe("disputed");
    expect(apply).not.toHaveBeenCalled();
    expect(revoke).not.toHaveBeenCalled();
  });

  it("unknown -> ignored tanpa sentuhan DB", async () => {
    const res = await processProviderStatus(orderFixture(), { kind: "unknown", rawStatus: "partial_refund" }, { source: "webhook" });
    expect(res.outcome).toBe("ignored");
    expect(claim).not.toHaveBeenCalled();
    expect(transition).not.toHaveBeenCalled();
  });

  it("refund dengan nominal tak cocok -> amount_mismatch, tanpa transisi/revoke", async () => {
    const order = orderFixture({ status: "paid" });
    const res = await processProviderStatus(
      order,
      { kind: "refunded", rawStatus: "refund", amountIdr: 999 },
      { source: "webhook" },
    );
    expect(res.outcome).toBe("amount_mismatch");
    expect(transition).not.toHaveBeenCalled();
    expect(revoke).not.toHaveBeenCalled();
  });
});

describe("processProviderStatus — pemulihan klaim yatim (T2)", () => {
  const paidStatus = { kind: "paid" as const, amountIdr: 50000, currency: "IDR", rawStatus: "settlement", providerTxnId: "txn-1" };
  const orphan = (ageMs: number) =>
    orderFixture({
      status: "paid",
      paid_at: new Date(Date.now() - ageMs).toISOString(),
      entitlement_applied_at: null,
      updated_at: new Date(Date.now() - ageMs).toISOString(),
    });

  it("klaim lama tanpa penerapan & atribusi beda -> apply pemulihan + tandai", async () => {
    const order = orphan(5 * 60_000);
    getOrder.mockResolvedValue(order);
    getEnt.mockResolvedValue(null);
    const res = await processProviderStatus(order, paidStatus, { source: "reconcile" });
    expect(res.outcome).toBe("recovered:activated");
    expect(apply).toHaveBeenCalledWith(order.guild_id, 30, "midtrans", order.order_ref, "recovery_after_claim");
    expect(mark).toHaveBeenCalledWith(order.order_ref, "txn-1");
  });

  it("atribusi entitlement sudah menunjuk order ini -> hanya ditandai (recovered_marked)", async () => {
    const order = orphan(5 * 60_000);
    getOrder.mockResolvedValue(order);
    getEnt.mockResolvedValue({ provider_entitlement_id: order.order_ref } as never);
    const res = await processProviderStatus(order, paidStatus, { source: "webhook" });
    expect(res.outcome).toBe("recovered_marked");
    expect(apply).not.toHaveBeenCalled();
    expect(mark).toHaveBeenCalledWith(order.order_ref, "txn-1");
  });

  it("klaim masih segar (< 60 dtk) -> already_applied, penerapan lain tidak diganggu", async () => {
    const order = orphan(5_000);
    getOrder.mockResolvedValue(order);
    const res = await processProviderStatus(order, paidStatus, { source: "webhook" });
    expect(res.outcome).toBe("already_applied");
    expect(apply).not.toHaveBeenCalled();
    expect(mark).not.toHaveBeenCalled();
  });
});
