/**
 * Webhook Midtrans & Xendit:
 * - signature SHA512 Midtrans dihitung dari fixture + server key tes;
 *   1 char berubah / signature hilang -> 401 TANPA sentuhan data.
 * - Midtrans: notifikasi hanya PEMICU — status yang diproses berasal
 *   dari status API (fetchStatus), BUKAN body notifikasi, karena
 *   signature tidak mencakup transaction_status/fraud_status. Tes
 *   mengatur fixture status API lewat stub fetch global; regresi T1:
 *   body settlement bertanda tangan sah + API bilang capture/challenge
 *   -> TETAP pending.
 * - settlement (API) -> klaim menang -> apply sekali; event sama 2x ->
 *   klaim kedua kalah -> apply tetap sekali (durasi tak ganda).
 * - nominal/currency beda -> 400 amount_mismatch tanpa klaim.
 * - capture challenge tetap pending; expire -> expired; refund dari paid
 *   -> refunded + revoke proporsional. Order tak ditemukan -> 404.
 * - body JSON literal null -> 401 (bukan 500); provider tak
 *   terkonfigurasi -> 503.
 * - Xendit: token callback salah -> 401; PAID -> aktivasi; EXPIRED -> expired.
 */
import { createHash } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  withDbError: (fn: unknown) => fn,
  getBillingOrderByRef: vi.fn(),
  recordWebhookEvent: vi.fn(async () => true),
  claimBillingOrderPaid: vi.fn(async () => null),
  applyPaymentToEntitlement: vi.fn(async () => "activated"),
  transitionBillingOrder: vi.fn(async () => true),
  revokeEntitlementForRefund: vi.fn(async () => true),
  markBillingOrderApplied: vi.fn(async () => true),
  getEntitlement: vi.fn(async () => null),
}));

import * as db from "@/lib/db";
import { POST as midtransPost } from "../app/api/payments/webhook/midtrans/route";
import { POST as xenditPost } from "../app/api/payments/webhook/xendit/route";
import type { BillingOrder } from "@/lib/db";

const getOrder = vi.mocked(db.getBillingOrderByRef);
const recordEvent = vi.mocked(db.recordWebhookEvent);
const claim = vi.mocked(db.claimBillingOrderPaid);
const apply = vi.mocked(db.applyPaymentToEntitlement);
const transition = vi.mocked(db.transitionBillingOrder);
const revoke = vi.mocked(db.revokeEntitlementForRefund);
const mark = vi.mocked(db.markBillingOrderApplied);

const SERVER_KEY = "sk-test-midtrans";
const XENDIT_TOKEN = "xendit-callback-token-test";
const GUILD = "111111111111111111";
const REF = "FINCH-111111111111111111-M3ABCDEF-ABCD1234";
const XREF = "FINCH-111111111111111111-X3ABCDEF-ABCD1234";

const ENV_KEYS = ["MIDTRANS_SERVER_KEY", "XENDIT_SECRET_KEY", "XENDIT_CALLBACK_TOKEN"] as const;
const savedEnv: Record<string, string | undefined> = {};
for (const k of ENV_KEYS) savedEnv[k] = process.env[k];

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
    updated_at: "2026-10-23T00:00:00.000Z",
    ...overrides,
  };
}

function midtransBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const body: Record<string, unknown> = {
    order_id: REF,
    status_code: "200",
    gross_amount: "50000.00",
    transaction_status: "settlement",
    transaction_id: "txn-1",
    fraud_status: "accept",
    currency: "IDR",
    payment_type: "bank_transfer",
    ...overrides,
  };
  body.signature_key = createHash("sha512")
    .update(`${body.order_id}${body.status_code}${body.gross_amount}${SERVER_KEY}`)
    .digest("hex");
  return body;
}

function reqRaw(url: string, raw: string, headers: Record<string, string> = {}): Request {
  return new Request(url, {
    method: "POST",
    body: raw,
    headers: { "content-type": "application/json", ...headers },
  });
}

function midtransReq(body: Record<string, unknown>): Request {
  return reqRaw("http://localhost/api/payments/webhook/midtrans", JSON.stringify(body));
}

/** Fixture status API Midtrans (yang fetchStatus baca — BUKAN body webhook). */
function midtransStatusBody(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    order_id: REF,
    status_code: "200",
    gross_amount: "50000.00",
    transaction_status: "settlement",
    transaction_id: "txn-1",
    fraud_status: "accept",
    currency: "IDR",
    ...overrides,
  };
}

let statusFixture: Record<string, unknown> = midtransStatusBody();
const fetchMock = vi.fn(async () => ({
  ok: true,
  status: 200,
  json: async () => statusFixture,
}));

beforeEach(() => {
  vi.clearAllMocks();
  process.env.MIDTRANS_SERVER_KEY = SERVER_KEY;
  process.env.XENDIT_SECRET_KEY = "xnd-test-secret";
  process.env.XENDIT_CALLBACK_TOKEN = XENDIT_TOKEN;
  statusFixture = midtransStatusBody();
  vi.stubGlobal("fetch", fetchMock);
  getOrder.mockResolvedValue(orderFixture());
  recordEvent.mockResolvedValue(true);
  claim.mockResolvedValue(null);
  apply.mockResolvedValue("activated");
  transition.mockResolvedValue(true);
  revoke.mockResolvedValue(true);
  mark.mockResolvedValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
});

describe("Webhook Midtrans — verifikasi signature", () => {
  it("signature valid diterima; signature 1 char berubah ditolak 401 tanpa sentuhan data", async () => {
    statusFixture = midtransStatusBody({ transaction_status: "pending" });
    const okRes = await midtransPost(midtransReq(midtransBody({ transaction_status: "pending" })));
    expect(okRes.status).toBe(200);

    const bad = midtransBody();
    const sig = bad.signature_key as string;
    bad.signature_key = (sig[0] === "a" ? "b" : "a") + sig.slice(1);
    const callsBefore = recordEvent.mock.calls.length;
    const badRes = await midtransPost(midtransReq(bad));
    expect(badRes.status).toBe(401);
    expect(recordEvent.mock.calls.length).toBe(callsBefore);
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("tanpa signature_key -> 401", async () => {
    const body = midtransBody();
    delete body.signature_key;
    const res = await midtransPost(midtransReq(body));
    expect(res.status).toBe(401);
    expect(recordEvent).not.toHaveBeenCalled();
    expect(getOrder).not.toHaveBeenCalled();
  });
});

describe("Webhook Midtrans — pemrosesan status", () => {
  it("settlement -> klaim menang -> apply tepat sekali", async () => {
    const order = orderFixture();
    claim.mockResolvedValue({ order, previousStatus: "pending" });
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(200);
    const json = (await res.json()) as { ok: boolean; outcome: string };
    expect(json).toEqual({ ok: true, outcome: "applied:activated" });
    expect(recordEvent).toHaveBeenCalledTimes(1);
    expect(claim).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(GUILD, 30, "midtrans", REF, undefined);
  });

  it("order lama plan_id vip_30d tetap settle lewat webhook dari snapshot order", async () => {
    const order = orderFixture({ plan_id: "vip_30d" });
    getOrder.mockResolvedValue(order);
    claim.mockResolvedValue({ order, previousStatus: "pending" });
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(200);
    const json = (await res.json()) as { ok: boolean; outcome: string };
    expect(json).toEqual({ ok: true, outcome: "applied:activated" });
    expect(apply).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledWith(GUILD, 30, "midtrans", REF, undefined);
  });

  it("event sama dikirim 2x -> apply tetap sekali (klaim kedua kalah)", async () => {
    const order = orderFixture();
    claim
      .mockResolvedValueOnce({ order, previousStatus: "pending" })
      .mockResolvedValue(null);
    const body = midtransBody();
    const r1 = await midtransPost(midtransReq(body));
    const r2 = await midtransPost(midtransReq(body));
    expect(r1.status).toBe(200);
    expect(r2.status).toBe(200);
    const j2 = (await r2.json()) as { outcome: string };
    expect(j2.outcome).toBe("already_applied");
    expect(claim).toHaveBeenCalledTimes(2);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("dua settlement bersamaan -> hanya satu klaim menang, apply sekali", async () => {
    const order = orderFixture();
    let wins = 0;
    claim.mockImplementation(async () => {
      wins += 1;
      return wins === 1 ? { order, previousStatus: "pending" } : null;
    });
    const body = midtransBody();
    const [r1, r2] = await Promise.all([
      midtransPost(midtransReq(body)),
      midtransPost(midtransReq(body)),
    ]);
    expect(r1.status).toBe(200);
    expect(r2.status).toBe(200);
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("nominal beda (menurut status API) -> 400 amount_mismatch tanpa klaim/apply", async () => {
    statusFixture = midtransStatusBody({ gross_amount: "60000.00" });
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(400);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("amount_mismatch");
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("currency beda (menurut status API) -> 400 amount_mismatch", async () => {
    statusFixture = midtransStatusBody({ currency: "USD" });
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(400);
    expect(claim).not.toHaveBeenCalled();
  });

  it("REGRESI T1: body settlement bertanda tangan sah, API bilang capture+challenge -> tetap pending, TIDAK ada klaim", async () => {
    statusFixture = midtransStatusBody({
      transaction_status: "capture",
      fraud_status: "challenge",
    });
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(200);
    const json = (await res.json()) as { outcome: string };
    expect(json.outcome).toBe("pending");
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("status API tak terjangkau -> 502 agar provider retry, payload mentah tidak diproses", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(502);
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("order tidak ditemukan -> 404 (event tetap dicatat)", async () => {
    getOrder.mockResolvedValue(null);
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(404);
    expect(recordEvent).toHaveBeenCalledTimes(1);
    expect(apply).not.toHaveBeenCalled();
  });

  it("capture challenge (menurut status API) -> tetap pending, tidak ada klaim", async () => {
    statusFixture = midtransStatusBody({
      transaction_status: "capture",
      fraud_status: "challenge",
    });
    const res = await midtransPost(
      midtransReq(midtransBody({ transaction_status: "capture", fraud_status: "challenge" })),
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as { outcome: string };
    expect(json.outcome).toBe("pending");
    expect(transition).toHaveBeenCalledWith(REF, "pending", ["created"]);
    expect(claim).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("expire (menurut status API) -> order expired", async () => {
    statusFixture = midtransStatusBody({ transaction_status: "expire", status_code: "407" });
    const res = await midtransPost(
      midtransReq(midtransBody({ transaction_status: "expire", status_code: "407" })),
    );
    expect(res.status).toBe(200);
    expect(transition).toHaveBeenCalledWith(REF, "expired", ["created", "pending"]);
  });

  it("refund dari order paid -> refunded + revoke proporsional", async () => {
    statusFixture = midtransStatusBody({ transaction_status: "refund" });
    getOrder.mockResolvedValue(orderFixture({ status: "paid" }));
    const res = await midtransPost(
      midtransReq(midtransBody({ transaction_status: "refund" })),
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as { outcome: string };
    expect(json.outcome).toBe("refunded");
    expect(transition).toHaveBeenCalledWith(REF, "refunded", ["paid"]);
    expect(revoke).toHaveBeenCalledWith(GUILD, "midtrans", REF, 30);
  });

  it("provider order tidak cocok dengan endpoint -> 400", async () => {
    getOrder.mockResolvedValue(orderFixture({ provider: "xendit" }));
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(400);
    expect(apply).not.toHaveBeenCalled();
  });
});

describe("Webhook — ketahanan input & konfigurasi", () => {
  it("body JSON literal null -> 401 kedua provider (bukan 500), tanpa sentuhan data", async () => {
    const mRes = await midtransPost(
      reqRaw("http://localhost/api/payments/webhook/midtrans", "null"),
    );
    expect(mRes.status).toBe(401);
    const xRes = await xenditPost(
      reqRaw("http://localhost/api/payments/webhook/xendit", "null", {
        "x-callback-token": XENDIT_TOKEN,
      }),
    );
    expect(xRes.status).toBe(401);
    expect(recordEvent).not.toHaveBeenCalled();
    expect(claim).not.toHaveBeenCalled();
  });

  it("provider tak terkonfigurasi (server key hilang) -> 503 jujur", async () => {
    delete process.env.MIDTRANS_SERVER_KEY;
    const res = await midtransPost(midtransReq(midtransBody()));
    expect(res.status).toBe(503);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("provider_not_configured");
    expect(recordEvent).not.toHaveBeenCalled();
  });
});

describe("Webhook Xendit", () => {
  function xenditReq(body: Record<string, unknown>, token: string | null = XENDIT_TOKEN): Request {
    const headers: Record<string, string> = {};
    if (token !== null) headers["x-callback-token"] = token;
    return reqRaw("http://localhost/api/payments/webhook/xendit", JSON.stringify(body), headers);
  }

  const xenditOrder = () =>
    orderFixture({ order_ref: XREF, provider: "xendit", provider_txn_id: "inv-1" });

  it("token salah / hilang -> 401 tanpa sentuhan data", async () => {
    const body = { id: "inv-1", external_id: XREF, status: "PAID", amount: 50000, paid_amount: 50000, currency: "IDR" };
    expect((await xenditPost(xenditReq(body, "token-salah"))).status).toBe(401);
    expect((await xenditPost(xenditReq(body, null))).status).toBe(401);
    expect(recordEvent).not.toHaveBeenCalled();
    expect(apply).not.toHaveBeenCalled();
  });

  it("PAID -> klaim menang -> aktivasi", async () => {
    const order = xenditOrder();
    getOrder.mockResolvedValue(order);
    claim.mockResolvedValue({ order, previousStatus: "pending" });
    const res = await xenditPost(
      xenditReq({ id: "inv-1", external_id: XREF, status: "PAID", amount: 50000, paid_amount: 50000, currency: "IDR" }),
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as { outcome: string };
    expect(json.outcome).toBe("applied:activated");
    expect(apply).toHaveBeenCalledWith(GUILD, 30, "xendit", XREF, undefined);
  });

  it("EXPIRED -> order expired", async () => {
    getOrder.mockResolvedValue(xenditOrder());
    const res = await xenditPost(
      xenditReq({ id: "inv-1", external_id: XREF, status: "EXPIRED", amount: 50000, currency: "IDR" }),
    );
    expect(res.status).toBe(200);
    expect(transition).toHaveBeenCalledWith(XREF, "expired", ["created", "pending"]);
    expect(apply).not.toHaveBeenCalled();
  });
});
