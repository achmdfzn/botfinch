// lib/payments/types.ts — kontrak provider pembayaran.
// Semua provider (Midtrans, Xendit) berbicara ke service lewat tipe ini
// saja; service tidak tahu detail API masing-masing provider.

export type ProviderStatusKind =
  | "paid"
  | "pending"
  | "failed"
  | "expired"
  | "cancelled"
  | "refunded"
  | "disputed"
  | "unknown";

export interface ProviderStatus {
  kind: ProviderStatusKind;
  /** ID transaksi di sisi provider (Midtrans transaction_id / Xendit invoice id). */
  providerTxnId?: string;
  /**
   * Nominal dalam rupiah (integer). undefined = nominal tidak bisa
   * dipastikan dari payload provider — service WAJIB menolak settlement
   * dengan amountIdr undefined ('amount_mismatch'), tidak menebak.
   */
  amountIdr?: number;
  /** Mata uang seperti dilaporkan provider; selain 'IDR' ditolak service. */
  currency?: string;
  /** Status mentah provider (mis. 'settlement', 'PAID') untuk audit. */
  rawStatus: string;
  /** true bila provider melaporkan refund sebagian (informasi saja). */
  partial?: boolean;
}

export interface VerifiedEvent {
  orderRef: string;
  providerTxnId: string;
  status: ProviderStatus;
  /** Kunci dedup event untuk recordWebhookEvent (unik per event provider). */
  eventKey: string;
}

export interface CreateCheckoutInput {
  orderRef: string;
  amountIdr: number;
  description: string;
  successRedirectUrl: string;
  failureRedirectUrl: string;
}

export interface CreateCheckoutResult {
  providerTxnId: string;
  redirectUrl: string;
}

export interface PaymentProvider {
  id: "midtrans" | "xendit";
  createCheckout(input: CreateCheckoutInput): Promise<CreateCheckoutResult>;
  fetchStatus(orderRef: string, providerTxnId?: string): Promise<ProviderStatus>;
  /**
   * Verifikasi webhook dari raw body + headers. null = TIDAK terverifikasi
   * (signature/token salah atau payload rusak) — pemanggil wajib menjawab
   * 401 dan tidak mengubah data apa pun.
   */
  verifyWebhook(headers: Headers, rawBody: string): Promise<VerifiedEvent | null>;
}
