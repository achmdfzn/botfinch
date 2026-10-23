// lib/payments/xendit.ts — provider Xendit Invoice (legacy v2, hosted checkout).
// Referensi resmi (dibaca saat implementasi, lihat BILLING.md):
// - Create: POST https://api.xendit.co/v2/invoices, Basic base64(secretKey + ':'),
//   body external_id/amount/currency/success_redirect_url/failure_redirect_url/
//   invoice_duration (detik)/description; respons {id, invoice_url}.
// - Get: GET /v2/invoices/{id}. Status: PENDING / PAID / SETTLED / EXPIRED.
// - Webhook: header 'x-callback-token' harus sama dengan Webhook
//   Verification Token dari dashboard Xendit.
import { timingSafeEqualStr } from "./midtrans";
import type {
  CreateCheckoutInput,
  CreateCheckoutResult,
  PaymentProvider,
  ProviderStatus,
  VerifiedEvent,
} from "./types";

const API_BASE = "https://api.xendit.co";

function basicAuth(secretKey: string): string {
  return `Basic ${Buffer.from(`${secretKey}:`).toString("base64")}`;
}

interface XenditInvoiceBody {
  id?: unknown;
  external_id?: unknown;
  status?: unknown;
  amount?: unknown;
  paid_amount?: unknown;
  currency?: unknown;
}

function asAmount(v: unknown): number | undefined {
  return typeof v === "number" && Number.isFinite(v) ? v : undefined;
}

/**
 * Petakan invoice Xendit ke ProviderStatus.
 * PAID/SETTLED -> paid (nominal dari paid_amount bila ada, else amount);
 * PENDING -> pending; EXPIRED -> expired; selain itu unknown.
 */
export function mapXenditStatus(body: XenditInvoiceBody): ProviderStatus {
  const raw = typeof body.status === "string" ? body.status : "";
  let kind: ProviderStatus["kind"];
  switch (raw) {
    case "PAID":
    case "SETTLED":
      kind = "paid";
      break;
    case "PENDING":
      kind = "pending";
      break;
    case "EXPIRED":
      kind = "expired";
      break;
    default:
      kind = "unknown";
      break;
  }
  return {
    kind,
    providerTxnId: typeof body.id === "string" ? body.id : undefined,
    amountIdr: asAmount(body.paid_amount) ?? asAmount(body.amount),
    currency: typeof body.currency === "string" ? body.currency : undefined,
    rawStatus: raw || "unknown",
  };
}

export class XenditProvider implements PaymentProvider {
  readonly id = "xendit" as const;

  constructor(
    private readonly secretKey: string,
    private readonly callbackToken: string,
  ) {}

  async createCheckout(input: CreateCheckoutInput): Promise<CreateCheckoutResult> {
    const res = await fetch(`${API_BASE}/v2/invoices`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        Authorization: basicAuth(this.secretKey),
      },
      body: JSON.stringify({
        external_id: input.orderRef,
        amount: input.amountIdr,
        currency: "IDR",
        success_redirect_url: input.successRedirectUrl,
        failure_redirect_url: input.failureRedirectUrl,
        invoice_duration: 3600,
        description: input.description,
      }),
    });
    if (!res.ok) throw new Error("xendit_create_failed");
    const data = (await res.json()) as { id?: unknown; invoice_url?: unknown };
    if (typeof data.id !== "string" || typeof data.invoice_url !== "string") {
      throw new Error("xendit_create_invalid_response");
    }
    return { providerTxnId: data.id, redirectUrl: data.invoice_url };
  }

  async fetchStatus(_orderRef: string, providerTxnId?: string): Promise<ProviderStatus> {
    if (!providerTxnId) throw new Error("xendit_status_missing_invoice_id");
    const res = await fetch(`${API_BASE}/v2/invoices/${encodeURIComponent(providerTxnId)}`, {
      method: "GET",
      headers: {
        Accept: "application/json",
        Authorization: basicAuth(this.secretKey),
      },
    });
    if (!res.ok) throw new Error("xendit_status_failed");
    const data = (await res.json()) as XenditInvoiceBody;
    return mapXenditStatus(data);
  }

  async verifyWebhook(headers: Headers, rawBody: string): Promise<VerifiedEvent | null> {
    const token = headers.get("x-callback-token");
    if (!token || !timingSafeEqualStr(token, this.callbackToken)) return null;
    let body: XenditInvoiceBody;
    try {
      body = JSON.parse(rawBody) as XenditInvoiceBody;
    } catch {
      return null;
    }
    // JSON valid bisa berupa null / bukan objek: tolak, jangan crash.
    if (!body || typeof body !== "object") return null;
    if (typeof body.external_id !== "string" || !body.external_id) return null;
    const status = mapXenditStatus(body);
    return {
      orderRef: body.external_id,
      providerTxnId: status.providerTxnId ?? "",
      status,
      eventKey: `xendit:${body.external_id}:${status.rawStatus}:${status.providerTxnId ?? ""}`,
    };
  }
}

/** Instance provider bila secret key + callback token lengkap; selain itu null. */
export function createXenditProvider(): XenditProvider | null {
  const secretKey = process.env.XENDIT_SECRET_KEY;
  const callbackToken = process.env.XENDIT_CALLBACK_TOKEN;
  if (!secretKey || !callbackToken) return null;
  return new XenditProvider(secretKey, callbackToken);
}
