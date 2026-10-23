// lib/premium.ts — definisi tier Free/VIP + batas fitur (murni, tanpa env/secret).
// Dipakai route dashboard (kuota) dan diuji langsung; bot punya salinan
// logika efektif yang sama di sisi Python.

export const FEATURE_LIMITS = {
  custom_commands: { free: 10, vip: 100 },
  autoresponders: { free: 10, vip: 100 },
  giveaways_active: { free: 3, vip: 25 },
  selfrole_panels: { free: 3, vip: 25 },
  announcements_active: { free: 3, vip: 25 },
} as const;

export type FeatureCode = keyof typeof FEATURE_LIMITS;

export type EffectiveTier = "free" | "vip";

export interface EntitlementLike {
  tier?: string | null;
  status?: string | null;
  starts_at?: string | Date | null;
  expires_at?: string | Date | null;
}

function toDate(v: string | Date | null | undefined): Date | null {
  if (v === null || v === undefined) return null;
  const d = v instanceof Date ? v : new Date(v);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * Tier efektif dari baris entitlement pada waktu `now`:
 * "vip" HANYA bila baris ada, tier "vip", status "active",
 * sudah mulai (starts_at null atau <= now) dan belum kedaluwarsa
 * (expires_at null = permanen, atau > now). Selain itu "free".
 * Tanggal diterima sebagai string ISO atau Date atau null.
 */
export function getEffectiveTierFromRow(
  row: EntitlementLike | null | undefined,
  now: Date = new Date(),
): EffectiveTier {
  if (!row) return "free";
  if (row.tier !== "vip") return "free";
  if (row.status !== "active") return "free";
  const startsAt = toDate(row.starts_at);
  if (startsAt && startsAt.getTime() > now.getTime()) return "free";
  const expiresAt = toDate(row.expires_at);
  if (expiresAt && expiresAt.getTime() <= now.getTime()) return "free";
  return "vip";
}

/** Batas fitur untuk tier tertentu. */
export function getFeatureLimit(tier: EffectiveTier, featureCode: FeatureCode): number {
  return FEATURE_LIMITS[featureCode][tier];
}
