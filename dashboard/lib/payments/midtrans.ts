// lib/payments/midtrans.ts — provider Midtrans Snap (redirect).
// Referensi resmi (dibaca saat implementasi, lihat BILLING.md):
// - Snap create transaction: POST {snap}/snap/v1/transactions,
//   Authorization Basic base64(serverKey + ':'), respons {token, redirect_url}.
// - Notification: signature_key = SHA512(order_id+status_code+gross_amount+serverKey).
// - GET status: GET {api}/v2/{order_id}/status.
import { createHash, timingSafeEqual } from "node:crypto";
import type {
  CreateCheckoutInput,
  CreateCheckoutResult,
  PaymentProvider,
  ProviderStatus,
  VerifiedEvent,
} from "./types";

function basicAuth(serverKey: string): string {
  return `Basic ${Buffer.from(`${serverKey}:`).toString("base64")}`;
}

/** Perbandingan string timing-safe; beda panjang = langsung false. */
export function timingSafeEqualStr(a: string, b: string): boolean {
  const ba = Buffer.from(a);
  const bb = Buffer.from(b);
  return ba.length === bb.length && timingSafeEqual(ba, bb);
}

/**
 * Parse gross_amount Midtrans. Format resmi: string desimal 2 angka di
 * belakang koma (mis. "50000.00"). Hanya sen "00" yang diterima sebagai
 * integer rupiah; pola lain (termasuk sen != 00) = undefined agar service
 * menolak settlement sebagai amount_mismatch alih-alih menebak nominal.
 */
export function parseMidtransGrossAmount(v: unknown): number | undefined {
  if (typeof v !== "string") return undefined;
  const m = /^(\d+)\.(\d{2})$/.exec(v);
  if (!m || m[2] !== "00") return undefined;
  const n = Number(m[1]);
  return Number.isSafeInteger(n) ? n : undefined;
}

interface MidtransStatusBody {
  transaction_status?: unknown;
  fraud_status?: unknown;
  gross_amount?: unknown;
  currency?: unknown;
  transaction_id?: unknown;
  order_id?: unknown;
  status_code?: unknown;
  signature_key?: unknown;
}

/**
 * Petakan payload status/notifikasi Midtrans ke ProviderStatus.
 * - settlement -> paid
 * - capture: fraud accept -> paid; challenge -> PENDING (bukan paid —
 *   dana belum pasti); deny -> failed; tanpa fraud_status (metode
 *   non-kartu) -> paid.
 * - partial_refund / partial_chargeback -> unknown DENGAN SENGAJA:
 *   kebijakan Finch hanya refund PENUH yang mencabut entitlement
 *   (lihat BILLING.md); service menjawab 'ignored' untuk unknown.
 * - chargeback -> disputed. Selain itu unknown.
 */
export function mapMidtransStatus(body: MidtransStatusBody): ProviderStatus {
  const raw = typeof body.transaction_status === "string" ? body.transaction_status : "";
  const fraud = typeof body.fraud_status === "string" ? body.fraud_status : undefined;
  let kind: ProviderStatus["kind"];
  switch (raw) {
    case "settlement":
      kind = "paid";
      break;
    case "capture":
      if (fraud === "challenge") kind = "pending";
      else if (fraud === "deny") kind = "failed";
      else kind = "paid";
      break;
    case "pending":
    case "authorize":
      kind = "pending";
      break;
    case "deny":
      kind = "failed";
      break;
    case "cancel":
      kind = "cancelled";
      break;
    case "expire":
      kind = "expired";
      break;
    case "refund":
      kind = "refunded";
      break;
    case "chargeback":
      kind = "disputed";
      break;
    default:
      kind = "unknown";
      break;
  }
  return {
    kind,
    providerTxnId: typeof body.transaction_id === "string" ? body.transaction_id : undefined,
    amountIdr: parseMidtransGrossAmount(body.gross_amount),
    currency: typeof body.currency === "string" ? body.currency : undefined,
    rawStatus: raw || "unknown",
    partial: raw === "partial_refund" || raw === "partial_chargeback" ? true : undefined,
  };
}

export class MidtransProvider implements PaymentProvider {
  readonly id = "midtrans" as const;

  constructor(
    private readonly serverKey: string,
    private readonly isProduction: boolean,
  ) {}

  private get snapBase(): string {
    return this.isProduction
      ? "https://app.midtrans.com"
      : "https://app.sandbox.midtrans.com";
  }

  private get apiBase(): string {
    return this.isProduction
      ? "https://api.midtrans.com"
      : "https://api.sandbox.midtrans.com";
  }

  async createCheckout(input: CreateCheckoutInput): Promise<CreateCheckoutResult> {
    const res = await fetch(`${this.snapBase}/snap/v1/transactions`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: basicAuth(this.serverKey),
      },
      body: JSON.stringify({
        transaction_details: {
          order_id: input.orderRef,
          gross_amount: input.amountIdr,
        },
        item_details: [
          {
            id: "vip_30d",
            price: input.amountIdr,
            quantity: 1,
            name: input.description.slice(0, 50),
          },
        ],
        callbacks: { finish: input.successRedirectUrl },
        // Objek expiry Snap resmi: { unit, duration } (docs "JSON Objects"
        // + "Expire a Snap Session") — 60 menit selaras expiresAt order.
        expiry: { unit: "minutes", duration: 60 },
      }),
    });
    if (!res.ok) throw new Error("midtrans_create_failed");
    const data = (await res.json()) as { token?: unknown; redirect_url?: unknown };
    if (typeof data.token !== "string" || typeof data.redirect_url !== "string") {
      throw new Error("midtrans_create_invalid_response");
    }
    return { providerTxnId: data.token, redirectUrl: data.redirect_url };
  }

  async fetchStatus(orderRef: string): Promise<ProviderStatus> {
    const res = await fetch(
      `${this.apiBase}/v2/${encodeURIComponent(orderRef)}/status`,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: basicAuth(this.serverKey),
        },
      },
    );
    if (!res.ok) throw new Error("midtrans_status_failed");
    const data = (await res.json()) as MidtransStatusBody;
    return mapMidtransStatus(data);
  }

  async verifyWebhook(_headers: Headers, rawBody: string): Promise<VerifiedEvent | null> {
    let body: MidtransStatusBody;
    try {
      body = JSON.parse(rawBody) as MidtransStatusBody;
    } catch {
      return null;
    }
    // JSON valid bisa berupa null / bukan objek (mis. body "null"):
    // tolak sebagai tidak valid, jangan sampai TypeError jadi 500.
    if (!body || typeof body !== "object") return null;
    const orderId = typeof body.order_id === "string" ? body.order_id : null;
    const statusCode = typeof body.status_code === "string" ? body.status_code : null;
    const grossAmount = typeof body.gross_amount === "string" ? body.gross_amount : null;
    const signatureKey = typeof body.signature_key === "string" ? body.signature_key : null;
    if (!orderId || !statusCode || !grossAmount || !signatureKey) return null;
    // Rumus resmi: SHA512(order_id + status_code + gross_amount + ServerKey)
    // dengan gross_amount mentah dari payload (jangan diformat ulang).
    const expected = createHash("sha512")
      .update(orderId + statusCode + grossAmount + this.serverKey)
      .digest("hex");
    if (!timingSafeEqualStr(expected, signatureKey)) return null;
    const status = mapMidtransStatus(body);
    return {
      orderRef: orderId,
      providerTxnId: status.providerTxnId ?? "",
      status,
      eventKey: `midtrans:${orderId}:${status.rawStatus}:${status.providerTxnId ?? ""}`,
    };
  }
}

/** Instance provider bila MIDTRANS_SERVER_KEY ada; selain itu null. */
export function createMidtransProvider(): MidtransProvider | null {
  const serverKey = process.env.MIDTRANS_SERVER_KEY;
  if (!serverKey) return null;
  return new MidtransProvider(serverKey, process.env.MIDTRANS_IS_PRODUCTION === "true");
}
