import Link from "next/link";
import { countActiveAnnouncements, getEntitlement } from "@/lib/db";
import { FEATURE_LIMITS, getEffectiveTierFromRow, type FeatureCode } from "@/lib/premium";
import { fmt, getDict, getLang } from "@/lib/i18n";

/**
 * Kartu status paket (Free/VIP) untuk halaman utama dashboard per-server.
 * Server Component: membaca entitlement dari Postgres (sumber kebenaran)
 * lewat lib/db, lalu menghitung tier efektif lewat lib/premium.
 *
 * Kegagalan baca entitlement TIDAK boleh merusak halaman server: komponen
 * me-render null. Kegagalan hitung pemakaian pengumuman hanya menyembunyikan
 * baris pemakaian, bukan seluruh kartu.
 */
export default async function PremiumStatus({ guildId }: { guildId: string }) {
  const lang = await getLang();
  const dict = getDict(lang);
  const p = dict.premium;
  const locale = lang === "en" ? "en-US" : "id-ID";

  let row: Awaited<ReturnType<typeof getEntitlement>>;
  try {
    row = await getEntitlement(guildId);
  } catch {
    return null;
  }

  const tier = getEffectiveTierFromRow(row);
  const isVip = tier === "vip";

  let announcementsUsed: number | null = null;
  try {
    announcementsUsed = await countActiveAnnouncements(guildId);
  } catch {
    announcementsUsed = null;
  }

  const statusText = !row
    ? p.statusNone
    : row.status === "active"
      ? p.statusActive
      : row.status === "revoked"
        ? p.statusRevoked
        : row.status === "expired"
          ? p.statusExpired
          : row.status;

  const expiryText = row?.expires_at
    ? fmt(p.expiresAt, { date: formatTanggal(row.expires_at, locale) })
    : isVip
      ? p.permanent
      : p.noExpiry;

  const featureCodes = Object.keys(FEATURE_LIMITS) as FeatureCode[];

  return (
    <section
      aria-label={p.title}
      className="mb-6 rounded-2xl border border-edge bg-panel p-5 sm:p-7"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-bold text-fg">{p.title}</h2>
          <p className="mt-1 text-sm text-muted">{p.subtitle}</p>
        </div>
        <span
          className={`rounded-full px-3 py-1 text-xs font-semibold ${
            isVip ? "bg-brand/15 text-brand" : "bg-edge text-muted"
          }`}
        >
          {isVip ? p.tierVip : p.tierFree}
        </span>
      </div>

      <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs text-muted">{p.currentTierLabel}</dt>
          <dd className="mt-0.5 font-semibold text-fg">{isVip ? p.tierVip : p.tierFree}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{p.statusLabel}</dt>
          <dd className="mt-0.5 font-semibold text-fg">{statusText}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted">{p.expiresLabel}</dt>
          <dd className="mt-0.5 font-semibold text-fg">{expiryText}</dd>
        </div>
      </dl>

      {announcementsUsed !== null && (
        <p className="mt-3 text-sm text-muted">
          {fmt(p.usageAnnouncements, {
            used: announcementsUsed,
            limit: FEATURE_LIMITS.announcements_active[tier],
          })}
        </p>
      )}

      <h3 className="mt-5 text-sm font-semibold text-fg">{p.limitsTitle}</h3>
      <div className="mt-2 overflow-x-auto rounded-xl border border-edge">
        <table className="w-full min-w-[420px] text-left text-sm">
          <thead>
            <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
              <th scope="col" className="px-4 py-2.5 font-medium">{p.colFeature}</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">{p.colFree}</th>
              <th scope="col" className="px-4 py-2.5 text-right font-medium">{p.colVip}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-edge">
            {featureCodes.map((code) => (
              <tr key={code}>
                <td className="px-4 py-2.5 text-fg">{p.features[code]}</td>
                <td
                  className={`px-4 py-2.5 text-right ${
                    isVip ? "text-muted" : "font-semibold text-fg"
                  }`}
                >
                  {FEATURE_LIMITS[code].free}
                </td>
                <td
                  className={`px-4 py-2.5 text-right ${
                    isVip ? "font-semibold text-brand" : "text-muted"
                  }`}
                >
                  {FEATURE_LIMITS[code].vip}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!isVip && (
        <div className="mt-4 border-t border-edge pt-4">
          <p className="text-sm font-semibold text-fg">{p.upgradeTitle}</p>
          <p className="mt-1 text-sm text-muted">{p.upgradeBody}</p>
          <Link
            href={`/dashboard/${guildId}/billing`}
            className="mt-3 inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
          >
            {dict.guild.common.quota.upgradeCta}
          </Link>
        </div>
      )}
    </section>
  );
}

function formatTanggal(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
