/**
 * Tes fungsi billing di lib/db (Worker C — subscription/entitlement + DB):
 * bentuk SQL & pemetaan hasil untuk order billing, klaim pembayaran
 * atomik, dedupe webhook, transisi kondisional, dan penerapan pembayaran
 * ke entitlement (4 outcome). Mengikuti pola mock @vercel/postgres di
 * db-announcement-sent.test.ts, diperluas dengan handler per-teks-SQL
 * agar fungsi multi-statement (getEntitlement/ensureEntitlement adalah
 * fungsi internal satu file yang tidak bisa di-mock terpisah) bisa diuji
 * lewat baris-baris sql yang dikembalikan mock.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

const sqlCalls: { text: string; values: unknown[] }[] = [];
type Row = Record<string, unknown>;
let sqlHandler: (text: string, values: unknown[]) => Row[] = () => [];

vi.mock("@vercel/postgres", () => ({
  sql: (strings: TemplateStringsArray, ...values: unknown[]) => {
    const text = strings.join(" ");
    sqlCalls.push({ text, values });
    return Promise.resolve({ rows: sqlHandler(text, values) });
  },
}));

import {
  applyPaymentToEntitlement,
  claimBillingOrderPaid,
  createBillingOrder,
  expireStaleBillingOrders,
  findActiveBillingOrder,
  getBillingOrderByRef,
  listBillingOrders,
  markBillingOrderApplied,
  recordWebhookEvent,
  revokeEntitlementForRefund,
  setBillingOrderProviderInfo,
  touchBillingOrderReconcile,
  transitionBillingOrder,
} from "./db";

const DAY_MS = 24 * 60 * 60 * 1000;
const CREATED = new Date("2026-10-23T00:00:00.000Z");
const EXPIRES = new Date("2026-10-24T00:00:00.000Z");

function orderRow(overrides: Row = {}): Row {
  return {
    id: 7,
    order_ref: "ord-123",
    buyer_user_id: "user-1",
    guild_id: "guild-1",
    plan_id: "vip-30d",
    amount_idr: 25000,
    currency: "IDR",
    duration_days: 30,
    status: "created",
    provider: "mockpay",
    provider_txn_id: null,
    provider_redirect_url: null,
    created_at: CREATED,
    expires_at: EXPIRES,
    paid_at: null,
    entitlement_applied_at: null,
    updated_at: CREATED,
    ...overrides,
  };
}

function entitlementRow(overrides: Row = {}): Row {
  return {
    guild_id: "guild-1",
    tier: "free",
    status: "active",
    source: "default",
    starts_at: null,
    expires_at: null,
    provider_entitlement_id: null,
    provider_subscription_id: null,
    granted_by: null,
    note: null,
    bot_present: true,
    first_seen_at: CREATED,
    last_seen_at: CREATED,
    created_at: CREATED,
    updated_at: CREATED,
    ...overrides,
  };
}

/** Handler untuk alur entitlement: SELECT membaca `ent`, sisanya kosong / sukses. */
function entitlementHandler(ent: Row) {
  return (text: string): Row[] => {
    if (text.includes("SELECT * FROM guild_entitlements")) return [ent];
    if (text.includes("UPDATE guild_entitlements")) return [{ guild_id: "guild-1" }];
    return [];
  };
}

function callsContaining(fragment: string) {
  return sqlCalls.filter((c) => c.text.includes(fragment));
}

beforeEach(() => {
  sqlCalls.length = 0;
  sqlHandler = () => [];
  // getEntitlement/ensureEntitlement & pembaca billing menjaga dbConfigured().
  process.env.POSTGRES_URL = "postgres://test:test@localhost/test";
});

describe("createBillingOrder", () => {
  it("INSERT status 'created' dan memetakan baris RETURNING ke BillingOrder ISO", async () => {
    sqlHandler = () => [orderRow()];
    const order = await createBillingOrder({
      orderRef: "ord-123",
      buyerUserId: "user-1",
      guildId: "guild-1",
      planId: "vip-30d",
      amountIdr: 25000,
      durationDays: 30,
      provider: "mockpay",
      expiresAt: EXPIRES.toISOString(),
    });
    expect(order).toMatchObject({
      id: 7,
      order_ref: "ord-123",
      buyer_user_id: "user-1",
      guild_id: "guild-1",
      plan_id: "vip-30d",
      amount_idr: 25000,
      currency: "IDR",
      duration_days: 30,
      status: "created",
      provider: "mockpay",
      provider_txn_id: null,
      provider_redirect_url: null,
      paid_at: null,
      entitlement_applied_at: null,
    });
    expect(order.created_at).toBe(CREATED.toISOString());
    expect(order.expires_at).toBe(EXPIRES.toISOString());
    expect(sqlCalls).toHaveLength(1);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("INSERT INTO billing_orders");
    expect(text).toContain("'created'");
    expect(text).toContain("RETURNING *");
    for (const v of ["ord-123", "user-1", "guild-1", "vip-30d", 25000, "IDR", 30, "mockpay"]) {
      expect(values).toContain(v);
    }
  });
});

describe("getBillingOrderByRef / findActiveBillingOrder / listBillingOrders", () => {
  it("getBillingOrderByRef: baris -> order, kosong -> null", async () => {
    sqlHandler = () => [orderRow()];
    expect((await getBillingOrderByRef("ord-123"))?.order_ref).toBe("ord-123");
    expect(sqlCalls[0].values).toContain("ord-123");
    sqlHandler = () => [];
    expect(await getBillingOrderByRef("tidak-ada")).toBeNull();
  });

  it("findActiveBillingOrder hanya status created/pending yang belum kedaluwarsa, terbaru", async () => {
    sqlHandler = () => [orderRow({ status: "pending" })];
    const found = await findActiveBillingOrder("guild-1", "vip-30d");
    expect(found?.status).toBe("pending");
    const { text, values } = sqlCalls[0];
    expect(text).toContain("status IN ('created', 'pending')");
    expect(text).toContain("expires_at > NOW()");
    expect(text).toContain("ORDER BY id DESC");
    expect(text).toContain("LIMIT 1");
    expect(values).toContain("guild-1");
    expect(values).toContain("vip-30d");
    sqlHandler = () => [];
    expect(await findActiveBillingOrder("guild-1", "vip-30d")).toBeNull();
  });

  it("listBillingOrders terbaru dulu dengan limit default 20", async () => {
    sqlHandler = () => [orderRow({ id: 9 }), orderRow({ id: 8 })];
    const list = await listBillingOrders("guild-1");
    expect(list.map((o) => o.id)).toEqual([9, 8]);
    expect(sqlCalls[0].text).toContain("ORDER BY id DESC");
    expect(sqlCalls[0].values).toContain(20);
    await listBillingOrders("guild-1", 5);
    expect(sqlCalls[1].values).toContain(5);
  });
});

describe("setBillingOrderProviderInfo", () => {
  it("set txn/redirect dan menaikkan created -> pending secara kondisional", async () => {
    sqlHandler = () => [{ id: 7 }];
    const ok = await setBillingOrderProviderInfo("ord-123", "txn-9", "https://pay.example/ord-123");
    expect(ok).toBe(true);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("provider_txn_id =");
    expect(text).toContain("provider_redirect_url =");
    expect(text).toContain("CASE WHEN status = 'created' THEN 'pending' ELSE status END");
    expect(text).toContain("updated_at = NOW()");
    expect(values).toContain("txn-9");
    expect(values).toContain("https://pay.example/ord-123");
    sqlHandler = () => [];
    expect(await setBillingOrderProviderInfo("tidak-ada", null, null)).toBe(false);
  });
});

describe("transitionBillingOrder", () => {
  it("UPDATE kondisional status = ANY(fromAllowed); true bila ada baris", async () => {
    sqlHandler = () => [{ id: 7 }];
    const ok = await transitionBillingOrder("ord-123", "expired", ["created", "pending"]);
    expect(ok).toBe(true);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("UPDATE billing_orders");
    expect(text).toContain("status = ANY(");
    expect(text).toContain("::text[]");
    expect(text).toContain("RETURNING id");
    expect(values).toContain("expired");
    expect(values).toContain("ord-123");
    // Template sql hanya menerima Primitive: daftar status dikirim
    // sebagai satu string literal array Postgres.
    expect(values).toContain('{"created","pending"}');
  });

  it("false bila tidak ada baris cocok, dan tanpa query bila fromAllowed kosong", async () => {
    sqlHandler = () => [];
    expect(await transitionBillingOrder("ord-123", "paid", ["pending"])).toBe(false);
    sqlCalls.length = 0;
    expect(await transitionBillingOrder("ord-123", "paid", [])).toBe(false);
    expect(sqlCalls).toHaveLength(0);
  });
});

describe("recordWebhookEvent", () => {
  it("INSERT ... ON CONFLICT DO NOTHING: event baru true, duplikat false (dedupe)", async () => {
    sqlHandler = () => [{ id: 1 }];
    expect(await recordWebhookEvent("mockpay", "evt-1", "ord-123", "settlement")).toBe(true);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("INSERT INTO billing_webhook_events");
    expect(text).toContain("ON CONFLICT (event_key) DO NOTHING");
    expect(values).toEqual(["mockpay", "evt-1", "ord-123", "settlement"]);
    sqlHandler = () => [];
    expect(await recordWebhookEvent("mockpay", "evt-1", "ord-123", "settlement")).toBe(false);
  });
});

describe("claimBillingOrderPaid", () => {
  it("menang: satu statement CTE atomik, order terpetakan + previousStatus terbaca", async () => {
    sqlHandler = () => [
      orderRow({
        status: "paid",
        provider_txn_id: "txn-9",
        paid_at: CREATED,
        entitlement_applied_at: CREATED,
        previous_status: "pending",
      }),
    ];
    const claim = await claimBillingOrderPaid("ord-123", "txn-9");
    expect(sqlCalls).toHaveLength(1);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("WITH prev AS");
    expect(text).toContain("previous_status");
    expect(text).toContain("entitlement_applied_at IS NULL");
    expect(text).toContain("NOT IN ('failed', 'cancelled', 'refunded', 'disputed')");
    expect(text).toContain("COALESCE(b.provider_txn_id,");
    expect(text).toContain("status = 'paid'");
    // Penanda klaim (paid_at) terpisah dari penanda penerapan: klaim
    // TIDAK BOLEH menyetel entitlement_applied_at — itu tugas
    // markBillingOrderApplied setelah apply berhasil (pemulihan T2).
    expect(text).toContain("paid_at IS NULL");
    expect(text).not.toContain("entitlement_applied_at = NOW()");
    expect(values).toContain("ord-123");
    expect(values).toContain("txn-9");
    expect(claim?.previousStatus).toBe("pending");
    expect(claim?.order.status).toBe("paid");
    expect(claim?.order.provider_txn_id).toBe("txn-9");
    expect(claim?.order.paid_at).toBe(CREATED.toISOString());
    expect(claim?.order.entitlement_applied_at).toBe(CREATED.toISOString());
    // previous_status adalah kolom bantu klaim, bukan field BillingOrder.
    expect(claim?.order).not.toHaveProperty("previous_status");
  });

  it("kalah (sudah diterapkan / status terminal / tidak ada): null", async () => {
    sqlHandler = () => [];
    expect(await claimBillingOrderPaid("ord-123", "txn-9")).toBeNull();
    expect(sqlCalls).toHaveLength(1);
  });
});

describe("markBillingOrderApplied & touch & expireStale", () => {
  it("markBillingOrderApplied: set penanda penerapan kondisional, true bila baris ditandai", async () => {
    sqlHandler = () => [{ id: 7 }];
    expect(await markBillingOrderApplied("ord-123", "txn-9")).toBe(true);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("entitlement_applied_at = NOW()");
    expect(text).toContain("entitlement_applied_at IS NULL");
    expect(values).toContain("ord-123");
    sqlHandler = () => [];
    expect(await markBillingOrderApplied("ord-123", "txn-9")).toBe(false);
  });

  it("touchBillingOrderReconcile: hanya order created/pending yang disentuh", async () => {
    await touchBillingOrderReconcile("ord-123");
    expect(sqlCalls[0].text).toContain("status IN ('created', 'pending')");
    expect(sqlCalls[0].text).toContain("updated_at = NOW()");
  });

  it("expireStaleBillingOrders: tutup order basi menurut expires_at, kembalikan jumlah", async () => {
    sqlHandler = () => [{ id: 1 }, { id: 2 }];
    expect(await expireStaleBillingOrders("guild-1", "vip_30d")).toBe(2);
    const { text, values } = sqlCalls[0];
    expect(text).toContain("status = 'expired'");
    expect(text).toContain("expires_at <= NOW()");
    expect(values).toEqual(["guild-1", "vip_30d"]);
  });
});

describe("applyPaymentToEntitlement", () => {
  it("activated: guild free -> VIP payment 30 hari, audit 'grant' memuat order_ref", async () => {
    sqlHandler = entitlementHandler(entitlementRow());
    const result = await applyPaymentToEntitlement("guild-1", 30, "mockpay", "ord-123");
    expect(result).toBe("activated");
    const updates = callsContaining("UPDATE guild_entitlements");
    expect(updates).toHaveLength(1);
    expect(updates[0].text).toContain("source = 'payment'");
    // Perpanjangan dihitung di SQL dari baris terkunci (anti lost-update),
    // dan order pendana dicatat di provider_entitlement_id.
    expect(updates[0].text).toContain("make_interval");
    expect(updates[0].text).toContain("provider_entitlement_id");
    expect(updates[0].values).toContain("system:mockpay");
    expect(updates[0].values).toContain(30);
    expect(updates[0].values).toContain("ord-123");
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits).toHaveLength(1);
    expect(audits[0].values).toContain("grant");
    expect(audits[0].values).toContain("system:mockpay");
    expect(String(audits[0].values[audits[0].values.length - 1])).toContain("payment");
    expect(String(audits[0].values[audits[0].values.length - 1])).toContain("ord-123");
  });

  it("extended: VIP aktif belum kedaluwarsa diperpanjang dari expires_at lama, starts_at dipertahankan", async () => {
    const oldStarts = "2026-10-01T00:00:00.000Z";
    const oldExpires = new Date(Date.now() + 10 * DAY_MS).toISOString();
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "active", source: "payment", starts_at: oldStarts, expires_at: oldExpires }),
    );
    const result = await applyPaymentToEntitlement("guild-1", 30, "mockpay", "ord-456", "perpanjang");
    expect(result).toBe("extended");
    const updates = callsContaining("UPDATE guild_entitlements");
    expect(updates).toHaveLength(1);
    // SQL memakai cabang aktif: expires_at lama + make_interval, starts_at dipertahankan.
    expect(updates[0].text).toContain("expires_at + make_interval");
    expect(updates[0].text).toContain("THEN starts_at ELSE NOW()");
    expect(updates[0].values).toContain(30);
    expect(updates[0].values).toContain("ord-456");
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits[0].values).toContain("extend");
    expect(String(audits[0].values[audits[0].values.length - 1])).toContain("ord-456");
    expect(String(audits[0].values[audits[0].values.length - 1])).toContain("perpanjang");
  });

  it("activated dari VIP kedaluwarsa: VIP aktif yang sudah lewat masa -> 'activated' (bukan extended), starts_at direset SQL", async () => {
    const pastExpires = new Date(Date.now() - 5 * DAY_MS).toISOString();
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "active", source: "payment", starts_at: CREATED, expires_at: pastExpires }),
    );
    const result = await applyPaymentToEntitlement("guild-1", 30, "mockpay", "ord-789");
    expect(result).toBe("activated");
    const updates = callsContaining("UPDATE guild_entitlements");
    expect(updates).toHaveLength(1);
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits[0].values).toContain("grant");
  });

  it("noop_permanent: VIP aktif permanen tidak diubah, hanya audit payment_noop_permanent", async () => {
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "active", source: "owner_grant", starts_at: CREATED, expires_at: null }),
    );
    const result = await applyPaymentToEntitlement("guild-1", 30, "mockpay", "ord-123");
    expect(result).toBe("noop_permanent");
    expect(callsContaining("UPDATE guild_entitlements")).toHaveLength(0);
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits).toHaveLength(1);
    expect(audits[0].values).toContain("payment_noop_permanent");
  });

  it("blocked_suspended: guild suspended tidak diaktifkan pembayaran, hanya audit payment_blocked_suspended", async () => {
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "suspended", source: "payment", expires_at: EXPIRES }),
    );
    const result = await applyPaymentToEntitlement("guild-1", 30, "mockpay", "ord-123");
    expect(result).toBe("blocked_suspended");
    expect(callsContaining("UPDATE guild_entitlements")).toHaveLength(0);
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits).toHaveLength(1);
    expect(audits[0].values).toContain("payment_blocked_suspended");
  });
});

describe("revokeEntitlementForRefund", () => {
  it("mengurangi masa sebesar durasi order yang direfund (SQL proporsional) + audit 'refund'", async () => {
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "active", source: "payment", expires_at: EXPIRES }),
    );
    const ok = await revokeEntitlementForRefund("guild-1", "mockpay", "ord-123", 30);
    expect(ok).toBe(true);
    const updates = callsContaining("UPDATE guild_entitlements");
    expect(updates).toHaveLength(1);
    // Pengurangan di SQL: expires_at - make_interval(duration); status
    // menjadi 'revoked' hanya bila sisa masa habis (CASE di SQL).
    expect(updates[0].text).toContain("expires_at - make_interval");
    expect(updates[0].text).toContain("THEN 'revoked' ELSE 'active'");
    expect(updates[0].text).toContain("source = 'payment'");
    expect(updates[0].values).toContain(30);
    const audits = callsContaining("INSERT INTO entitlement_audit_log");
    expect(audits).toHaveLength(1);
    expect(audits[0].values).toContain("refund");
    expect(String(audits[0].values[audits[0].values.length - 1])).toContain("ord-123");
  });

  it("grant owner tidak tersentuh refund: false tanpa UPDATE/audit", async () => {
    sqlHandler = entitlementHandler(
      entitlementRow({ tier: "vip", status: "active", source: "owner_grant", expires_at: EXPIRES }),
    );
    const ok = await revokeEntitlementForRefund("guild-1", "mockpay", "ord-123", 30);
    expect(ok).toBe(false);
    expect(callsContaining("UPDATE guild_entitlements")).toHaveLength(0);
    expect(callsContaining("INSERT INTO entitlement_audit_log")).toHaveLength(0);
  });
});
