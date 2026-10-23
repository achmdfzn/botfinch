// lib/billing.ts — konfigurasi billing Finch Premium (murni env, tanpa DB).
// Harga TIDAK PERNAH datang dari client: satu-satunya sumber harga plan
// adalah env BILLING_VIP_30D_PRICE_IDR di server. Plan lain belum dijual.

export interface BillingPlan {
  id: string;
  durationDays: number;
  currency: "IDR";
}

export const PLANS: BillingPlan[] = [
  { id: "vip_30d", durationDays: 30, currency: "IDR" },
];

export function getPlan(id: unknown): BillingPlan | null {
  if (typeof id !== "string") return null;
  return PLANS.find((p) => p.id === id) ?? null;
}

/**
 * Harga VIP 30 hari dalam rupiah dari env BILLING_VIP_30D_PRICE_IDR.
 * WAJIB string digit murni (integer > 0, tanpa pemisah ribuan/desimal/
 * spasi). Nilai apa pun selain itu = plan tidak dijual (null), supaya
 * salah konfigurasi tidak pernah berubah jadi harga 0 / harga karangan.
 */
export function getVip30dPriceIdr(): number | null {
  const raw = process.env.BILLING_VIP_30D_PRICE_IDR;
  if (!raw || !/^\d+$/.test(raw)) return null;
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n <= 0) return null;
  return n;
}

export type PaymentProviderId = "midtrans" | "xendit";

/** Provider aktif dari env PAYMENT_PROVIDER; nilai lain = tidak ada. */
export function getActiveProviderId(): PaymentProviderId | null {
  const raw = process.env.PAYMENT_PROVIDER;
  return raw === "midtrans" || raw === "xendit" ? raw : null;
}

/**
 * Kelengkapan credential server-side per provider:
 * - midtrans: MIDTRANS_SERVER_KEY (dipakai Snap create + verifikasi
 *   signature webhook + GET status). MIDTRANS_CLIENT_KEY bersifat publik
 *   (untuk snap.js di browser bila nanti dipakai) dan TIDAK diwajibkan
 *   untuk alur redirect yang dipakai sekarang.
 * - xendit: XENDIT_SECRET_KEY (API) + XENDIT_CALLBACK_TOKEN (verifikasi
 *   webhook) — keduanya wajib, tanpa token callback webhook tak bisa
 *   diverifikasi sama sekali.
 */
export function providerCredentialsComplete(id: PaymentProviderId): boolean {
  if (id === "midtrans") {
    return Boolean(process.env.MIDTRANS_SERVER_KEY);
  }
  return Boolean(process.env.XENDIT_SECRET_KEY && process.env.XENDIT_CALLBACK_TOKEN);
}

/** Billing siap dipakai hanya bila provider + credential + harga valid. */
export function isBillingConfigured(): boolean {
  const provider = getActiveProviderId();
  if (!provider) return false;
  if (!providerCredentialsComplete(provider)) return false;
  return getVip30dPriceIdr() !== null;
}

// ---------------------------------------------------------------------------
// State machine order billing
// ---------------------------------------------------------------------------

export type BillingOrderStatus =
  | "created"
  | "pending"
  | "paid"
  | "failed"
  | "expired"
  | "cancelled"
  | "refunded"
  | "disputed";

/**
 * Transisi status order yang sah. Selain yang tercantum = ditolak.
 * - expired -> paid disengaja SAH: late settlement (pembeli membayar pas
 *   di batas kedaluwarsa) tetap menghormati uang yang sudah masuk; service
 *   menandainya dengan note 'late_settlement' di entitlement.
 * - failed/cancelled/refunded/disputed adalah terminal untuk settlement:
 *   service menjawab 'settlement_after_terminal' tanpa menerapkan apa pun.
 * - paid hanya bisa ke refunded/disputed.
 */
export const ORDER_TRANSITIONS: Record<BillingOrderStatus, readonly BillingOrderStatus[]> = {
  created: ["pending", "paid", "failed", "expired", "cancelled"],
  pending: ["paid", "failed", "expired", "cancelled"],
  expired: ["paid"],
  paid: ["refunded", "disputed"],
  failed: [],
  cancelled: [],
  refunded: [],
  disputed: [],
};

export function canTransitionOrder(from: string, to: string): boolean {
  const allowed = ORDER_TRANSITIONS[from as BillingOrderStatus];
  return allowed ? allowed.includes(to as BillingOrderStatus) : false;
}

/**
 * Daftar status sumber yang sah menuju `to`, diturunkan dari
 * ORDER_TRANSITIONS — inilah yang dipakai service sebagai fromAllowed
 * pada transitionBillingOrder, agar peta transisi di atas adalah
 * SUMBER TUNGGAL (bukan sekadar dokumentasi yang bisa divergen dari
 * penegakan di service/DB).
 */
export function transitionSources(to: BillingOrderStatus): BillingOrderStatus[] {
  return (Object.keys(ORDER_TRANSITIONS) as BillingOrderStatus[]).filter((from) =>
    ORDER_TRANSITIONS[from].includes(to),
  );
}
