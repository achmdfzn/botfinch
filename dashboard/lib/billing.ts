// lib/billing.ts — konfigurasi billing Finch Premium (murni env, tanpa DB).
// Harga TIDAK PERNAH datang dari client: sumber harga plan adalah harga
// default katalog di file ini, yang bisa dioverride oleh env
// BILLING_VIP_PRICE_IDR di server. Plan lain belum dijual.

export interface BillingPlan {
  id: string;
  durationDays: number;
  currency: "IDR";
}

/** Harga default katalog plan VIP (rupiah) bila env override tidak diisi. */
export const DEFAULT_VIP_PRICE_IDR = 65000;

export const PLANS: BillingPlan[] = [
  // "vip_monthly": 1 bulan didefinisikan resmi sebagai 30 hari.
  { id: "vip_monthly", durationDays: 30, currency: "IDR" },
];

export function getPlan(id: unknown): BillingPlan | null {
  if (typeof id !== "string") return null;
  return PLANS.find((p) => p.id === id) ?? null;
}

/**
 * Harga VIP bulanan (30 hari) dalam rupiah.
 * - env BILLING_VIP_PRICE_IDR tidak terisi / string kosong -> harga
 *   default katalog (DEFAULT_VIP_PRICE_IDR = 65000).
 * - env terisi string digit murni (integer > 0, tanpa pemisah ribuan/
 *   desimal/spasi) -> harga adalah nilai env itu (override).
 * - env terisi tetapi INVALID (non-digit, 0, negatif, desimal) -> null
 *   (billing nonaktif, fail-closed) dan dicatat lewat console.error:
 *   salah konfigurasi tidak pernah diam-diam jatuh ke harga default,
 *   harga 0, atau harga karangan.
 */
let defaultPriceWarningLogged = false;
const invalidPriceReasonsLogged = new Set<string>();

/**
 * Error harga invalid dicatat sekali per alasan per proses: env tidak
 * berubah antar-request, jadi alasan yang sama berulang adalah banjir
 * log yang sama; alasan berbeda tetap masing-masing tercatat.
 */
function logInvalidPrice(reason: string): void {
  if (invalidPriceReasonsLogged.has(reason)) return;
  invalidPriceReasonsLogged.add(reason);
  console.error(`BILLING_VIP_PRICE_IDR invalid (${reason}); billing dinonaktifkan (fail-closed).`);
}

export function getVipPriceIdr(): number | null {
  const raw = process.env.BILLING_VIP_PRICE_IDR;
  if (raw === undefined || raw === "") {
    // Harga default adalah keputusan produk yang sah, tetapi JANGAN
    // diam-diam: operator harus bisa melihat di log bahwa harga yang
    // ditagih berasal dari default katalog, bukan env eksplisit.
    // Diperingatkan sekali per proses agar tidak membanjiri log.
    if (!defaultPriceWarningLogged) {
      defaultPriceWarningLogged = true;
      console.warn(
        "BILLING_VIP_PRICE_IDR tidak diisi; memakai harga default katalog Rp65000 untuk plan vip_monthly.",
      );
    }
    return DEFAULT_VIP_PRICE_IDR;
  }
  if (!/^\d+$/.test(raw)) {
    // Nilai mentah TIDAK dicetak: env yang salah isi bisa memuat
    // karakter kontrol/newline yang menyuntik baris log palsu.
    logInvalidPrice(`panjang ${raw.length}, bukan digit murni > 0`);
    return null;
  }
  const n = Number(raw);
  if (!Number.isSafeInteger(n) || n <= 0) {
    logInvalidPrice(`panjang ${raw.length}, bukan integer aman > 0`);
    return null;
  }
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
  return getVipPriceIdr() !== null;
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
