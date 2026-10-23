/**
 * Route checkout billing:
 * - non-manager ditolak sebelum apa pun dibuat.
 * - billing tak terkonfigurasi -> 503 billing_not_configured.
 * - harga order SELALU dari env, field harga jahat di body diabaikan.
 * - order aktif yang sudah ada dipakai ulang (reused) tanpa order/fetch baru.
 * - order aktif menggantung TANPA tautan bayar -> ditutup failed, order
 *   baru dibuat (pembeli tidak terjebak). Order basi di-expire dulu.
 * - dua POST bersamaan: insert kedua kena unique violation indeks
 *   order-aktif -> order pemenang dikembalikan sebagai reused.
 * - plan asing -> 400; error provider -> order ditutup failed + 502 generik.
 */
import { NextResponse } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  dbConfigured: vi.fn(() => true),
  withDbError: (fn: unknown) => fn,
  createBillingOrder: vi.fn(async (input: Record<string, unknown>) => ({
    order_ref: input.orderRef,
    status: "created",
  })),
  findActiveBillingOrder: vi.fn(async () => null),
  expireStaleBillingOrders: vi.fn(async () => 0),
  setBillingOrderProviderInfo: vi.fn(async () => undefined),
  transitionBillingOrder: vi.fn(async () => true),
}));

vi.mock("@/lib/access", () => ({
  requireManager: vi.fn(async () => null),
  getSessionDiscordId: vi.fn(async () => "333333333333333333"),
}));

import * as access from "@/lib/access";
import * as db from "@/lib/db";
import { POST } from "../app/api/guilds/[id]/billing/checkout/route";

const manager = vi.mocked(access.requireManager);
const sessionId = vi.mocked(access.getSessionDiscordId);
const createOrder = vi.mocked(db.createBillingOrder);
const findActive = vi.mocked(db.findActiveBillingOrder);
const expireStale = vi.mocked(db.expireStaleBillingOrders);
const setProviderInfo = vi.mocked(db.setBillingOrderProviderInfo);
const transition = vi.mocked(db.transitionBillingOrder);

const GUILD = "111111111111111111";
const ctx = { params: Promise.resolve({ id: GUILD }) };

const ENV_KEYS = ["PAYMENT_PROVIDER", "MIDTRANS_SERVER_KEY", "BILLING_VIP_30D_PRICE_IDR", "APP_BASE_URL"] as const;
const savedEnv: Record<string, string | undefined> = {};
for (const k of ENV_KEYS) savedEnv[k] = process.env[k];

const fetchMock = vi.fn();

function reqJson(body: unknown): Request {
  return new Request(`http://localhost/api/guilds/${GUILD}/billing/checkout`, {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "content-type": "application/json" },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  manager.mockResolvedValue(null);
  sessionId.mockResolvedValue("333333333333333333");
  findActive.mockResolvedValue(null);
  expireStale.mockResolvedValue(0);
  createOrder.mockImplementation(async (input) => ({
    order_ref: input.orderRef,
    status: "created",
  }) as unknown as Awaited<ReturnType<typeof db.createBillingOrder>>);
  process.env.PAYMENT_PROVIDER = "midtrans";
  process.env.MIDTRANS_SERVER_KEY = "sk-test-server";
  process.env.BILLING_VIP_30D_PRICE_IDR = "50000";
  delete process.env.APP_BASE_URL;
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      token: "snap-token-1",
      redirect_url: "https://app.sandbox.midtrans.com/snap/v2/vtweb/snap-token-1",
    }),
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
});

describe("POST billing/checkout", () => {
  it("non-manager ditolak (respons requireManager diteruskan), tidak ada order", async () => {
    manager.mockResolvedValue(
      NextResponse.json({ error: "forbidden" }, { status: 403 }),
    );
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(403);
    expect(createOrder).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("billing tak terkonfigurasi (harga env kosong) -> 503 billing_not_configured", async () => {
    delete process.env.BILLING_VIP_30D_PRICE_IDR;
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(503);
    const json = (await res.json()) as { error: string };
    expect(json.error).toBe("billing_not_configured");
    expect(createOrder).not.toHaveBeenCalled();
  });

  it("plan asing -> 400, tidak ada order", async () => {
    const res = await POST(reqJson({ plan_id: "vip_365d" }), ctx);
    expect(res.status).toBe(400);
    expect(createOrder).not.toHaveBeenCalled();
  });

  it("harga dari env, BUKAN body (amount jahat diabaikan total)", async () => {
    const res = await POST(
      reqJson({ plan_id: "vip_30d", amount_idr: 1, price: 1, amount: 1, tier: "vip" }),
      ctx,
    );
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order_ref: string; redirect_url: string };
    expect(json.redirect_url).toBe(
      "https://app.sandbox.midtrans.com/snap/v2/vtweb/snap-token-1",
    );
    expect(json.order_ref).toMatch(new RegExp(`^FINCH-${GUILD}-[0-9A-Z]+-[0-9A-F]{8}$`));
    expect(createOrder).toHaveBeenCalledTimes(1);
    const arg = createOrder.mock.calls[0][0] as unknown as Record<string, unknown>;
    expect(arg.amountIdr).toBe(50000);
    expect(arg.planId).toBe("vip_30d");
    expect(arg.durationDays).toBe(30);
    expect(arg.provider).toBe("midtrans");
    expect(arg.buyerUserId).toBe("333333333333333333");
    // Nominal yang dikirim ke Midtrans pun harga env.
    const fetchBody = JSON.parse((fetchMock.mock.calls[0][1] as { body: string }).body) as {
      transaction_details: { gross_amount: number; order_id: string };
    };
    expect(fetchBody.transaction_details.gross_amount).toBe(50000);
    expect(fetchBody.transaction_details.order_id).toBe(json.order_ref);
    expect(setProviderInfo).toHaveBeenCalledWith(
      json.order_ref,
      "snap-token-1",
      "https://app.sandbox.midtrans.com/snap/v2/vtweb/snap-token-1",
    );
  });

  it("order aktif sudah ada -> reused, tanpa order/fetch baru", async () => {
    findActive.mockResolvedValue({
      order_ref: "FINCH-LAMA",
      provider_redirect_url: "https://app.sandbox.midtrans.com/snap/v2/vtweb/lama",
      status: "pending",
    } as never);
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order_ref: string; reused: boolean; redirect_url: string };
    expect(json).toEqual({
      order_ref: "FINCH-LAMA",
      redirect_url: "https://app.sandbox.midtrans.com/snap/v2/vtweb/lama",
      status: "pending",
      reused: true,
    });
    expect(createOrder).not.toHaveBeenCalled();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("provider error -> order ditutup failed + 502 tanpa detail internal", async () => {
    fetchMock.mockResolvedValue({ ok: false, json: async () => ({ error_messages: ["kredensial salah"] }) });
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(502);
    const json = (await res.json()) as { error: string };
    expect(json).toEqual({ error: "provider_error" });
    expect(transition).toHaveBeenCalledWith(expect.stringMatching(/^FINCH-/), "failed", ["created"]);
    expect(setProviderInfo).not.toHaveBeenCalled();
  });

  it("order aktif menggantung tanpa tautan bayar -> ditutup failed, order BARU dibuat", async () => {
    findActive.mockResolvedValue({
      order_ref: "FINCH-GANTUNG",
      provider_redirect_url: null,
      status: "created",
    } as never);
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order_ref: string; reused?: boolean };
    expect(json.order_ref).not.toBe("FINCH-GANTUNG");
    expect(json.reused).toBeUndefined();
    expect(transition).toHaveBeenCalledWith("FINCH-GANTUNG", "failed", ["created", "pending"]);
    expect(createOrder).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("dua POST bersamaan: unique violation -> order pemenang dikembalikan sebagai reused", async () => {
    createOrder.mockRejectedValueOnce(
      Object.assign(new Error("duplicate key value violates unique constraint"), { code: "23505" }),
    );
    findActive
      .mockResolvedValueOnce(null)
      .mockResolvedValue({
        order_ref: "FINCH-PEMENANG",
        provider_redirect_url: "https://app.sandbox.midtrans.com/snap/v2/vtweb/pemenang",
        status: "pending",
      } as never);
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(200);
    const json = (await res.json()) as { order_ref: string; reused: boolean };
    expect(json.order_ref).toBe("FINCH-PEMENANG");
    expect(json.reused).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
    // Order basi selalu di-expire sebelum pencarian order aktif.
    expect(expireStale).toHaveBeenCalledWith(GUILD, "vip_30d");
  });

  it("tanpa sesi (buyer null) -> 401", async () => {
    sessionId.mockResolvedValue(null);
    const res = await POST(reqJson({ plan_id: "vip_30d" }), ctx);
    expect(res.status).toBe(401);
    expect(createOrder).not.toHaveBeenCalled();
  });
});
