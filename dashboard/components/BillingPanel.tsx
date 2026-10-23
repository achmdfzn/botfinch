"use client";

import { useState } from "react";
import Link from "next/link";
import { useI18n } from "@/components/I18nProvider";
import { fmt, type Dict, type Lang } from "@/lib/i18n/client";
import { FEATURE_LIMITS, type FeatureCode } from "@/lib/premium";

export interface BillingOrderSummary {
  order_ref: string;
  plan_id: string;
  amount_idr: number;
  currency: string;
  status: string;
  provider_redirect_url: string | null;
  created_at: string | null;
  expires_at: string | null;
}

interface BillingPanelProps {
  guildId: string;
  tier: "free" | "vip";
  entitlementStatus: string | null;
  entitlementExpiresAt: string | null;
  billingConfigured: boolean;
  priceIdr: number | null;
  providerId: string | null;
  orders: BillingOrderSummary[];
  dict: Dict;
  lang: Lang;
}

const primaryBtnCls =
  "inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

const ghostBtnCls =
  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-4 text-sm font-medium text-fg hover:border-brand hover:text-brand focus-visible:outline-2 focus-visible:outline-brand";

const OPEN_STATUSES = new Set(["created", "pending"]);

function statusBadgeCls(status: string): string {
  switch (status) {
    case "paid":
      return "bg-green-500/10 text-green-400";
    case "created":
    case "pending":
      return "bg-yellow-500/10 text-yellow-400";
    case "failed":
    case "expired":
    case "cancelled":
      return "bg-red-500/10 text-red-400";
    default:
      return "bg-edge text-muted";
  }
}

/**
 * Panel billing per server: status paket saat ini, kartu plan VIP 30 hari
 * dengan checkout ke gerbang pembayaran, tabel perbandingan batas fitur
 * dari katalog FEATURE_LIMITS, dan riwayat pesanan.
 *
 * dict/lang diteruskan server lewat props sebagai nilai awal; nilai live
 * dari useI18n() dipakai agar pergantian bahasa tanpa reload tetap sinkron
 * (pola AdminPremium). Semua harga dan angka batas berasal dari props dan
 * katalog nyata, tidak pernah dikarang di komponen ini.
 */
export default function BillingPanel({
  guildId,
  tier,
  entitlementStatus,
  entitlementExpiresAt,
  billingConfigured,
  priceIdr,
  providerId,
  orders,
  dict: initialDict,
  lang: initialLang,
}: BillingPanelProps) {
  const { dict: liveDict, lang: liveLang } = useI18n();
  const dict = liveDict ?? initialDict;
  const lang = liveLang ?? initialLang;
  const b = dict.billing;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [checkingOut, setCheckingOut] = useState(false);
  const [checkoutError, setCheckoutError] = useState<string | null>(null);

  const isVip = tier === "vip";

  const entitlementStatusText = !entitlementStatus
    ? b.entitlementStatusNone
    : entitlementStatus === "active"
      ? b.entitlementStatusActive
      : entitlementStatus === "revoked"
        ? b.entitlementStatusRevoked
        : entitlementStatus === "expired"
          ? b.entitlementStatusExpired
          : entitlementStatus;

  const expiryText = entitlementExpiresAt
    ? fmt(b.expiresAt, { date: formatTanggal(entitlementExpiresAt, locale) })
    : isVip
      ? b.permanent
      : b.noExpiry;

  // Waktu acuan untuk cek kedaluwarsa pesanan aktif: diambil sekali saat
  // mount lewat lazy state agar render tetap murni (react-hooks/purity).
  const [now] = useState(() => Date.now());
  const activeOrder =
    orders.find(
      (o) =>
        OPEN_STATUSES.has(o.status) &&
        o.provider_redirect_url &&
        (!o.expires_at || new Date(o.expires_at).getTime() > now),
    ) ?? null;

  const featureCodes = Object.keys(FEATURE_LIMITS) as FeatureCode[];

  const orderStatusText = (status: string): string => {
    const map = b.orderStatus as Record<string, string>;
    return map[status] ?? b.orderStatus.unknown;
  };

  const planText = (planId: string): string =>
    planId === "vip_30d" ? b.planVip30d : planId;

  async function startCheckout() {
    if (checkingOut || !billingConfigured) return;
    setCheckingOut(true);
    setCheckoutError(null);
    try {
      const res = await fetch(`/api/guilds/${guildId}/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: "vip_30d" }),
      });
      const data: unknown = await res.json().catch(() => null);
      const payload =
        data && typeof data === "object" ? (data as Record<string, unknown>) : {};
      if (!res.ok) {
        const code = typeof payload.error === "string" ? payload.error : "";
        setCheckoutError(
          code === "billing_not_configured"
            ? b.checkoutErrorNotConfigured
            : code === "provider_error"
              ? b.checkoutErrorProvider
              : b.checkoutError,
        );
        return;
      }
      const redirectUrl =
        typeof payload.redirect_url === "string" ? payload.redirect_url : "";
      if (redirectUrl) {
        window.location.assign(redirectUrl);
        return;
      }
      setCheckoutError(b.checkoutErrorProvider);
    } catch {
      setCheckoutError(b.checkoutError);
    } finally {
      setCheckingOut(false);
    }
  }

  return (
    <div className="space-y-6">
      {/* Status paket saat ini */}
      <section
        aria-label={b.currentPlanTitle}
        className="rounded-2xl border border-edge bg-panel p-5 sm:p-7"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h2 className="text-lg font-bold text-fg">{b.currentPlanTitle}</h2>
          <span
            className={`rounded-full px-3 py-1 text-xs font-semibold ${
              isVip ? "bg-brand/15 text-brand" : "bg-edge text-muted"
            }`}
          >
            {isVip ? b.tierVip : b.tierFree}
          </span>
        </div>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs text-muted">{b.currentTierLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{isVip ? b.tierVip : b.tierFree}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{b.statusLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{entitlementStatusText}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{b.expiresLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{expiryText}</dd>
          </div>
        </dl>
      </section>

      {/* Pesanan aktif yang belum selesai */}
      {activeOrder && (
        <section
          aria-label={b.activeOrderTitle}
          className="rounded-2xl border border-edge bg-panel p-5 sm:p-7"
        >
          <h2 className="text-base font-bold text-fg">{b.activeOrderTitle}</h2>
          <p className="mt-1 text-sm text-muted">{b.activeOrderBody}</p>
          <p className="mt-2 text-sm text-fg">
            <span
              className={`mr-2 rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeCls(activeOrder.status)}`}
            >
              {orderStatusText(activeOrder.status)}
            </span>
            {planText(activeOrder.plan_id)} · {formatHarga(activeOrder.amount_idr, activeOrder.currency, locale)}
          </p>
          {activeOrder.expires_at && (
            <p className="mt-2 text-sm text-muted">
              {fmt(b.activeOrderExpires, { date: formatTanggal(activeOrder.expires_at, locale) })}
            </p>
          )}
          <div className="mt-4 flex flex-wrap gap-2">
            {activeOrder.provider_redirect_url && (
              <a href={activeOrder.provider_redirect_url} className={primaryBtnCls}>
                {b.continuePayment}
              </a>
            )}
            <Link
              href={`/dashboard/${guildId}/billing/orders/${activeOrder.order_ref}`}
              className={ghostBtnCls}
            >
              {b.viewOrderStatus}
            </Link>
          </div>
        </section>
      )}

      {/* Kartu plan VIP 30 hari + checkout */}
      <section
        aria-label={b.planTitle}
        className="rounded-2xl border border-edge bg-panel p-5 sm:p-7"
      >
        <h2 className="text-lg font-bold text-fg">{b.planTitle}</h2>
        <p className="mt-1 text-sm text-muted">{b.planDesc}</p>
        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted">{b.planDurationLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{b.planDurationValue}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{b.colAmount}</dt>
            <dd className="mt-0.5 font-semibold text-fg">
              {priceIdr !== null ? formatHarga(priceIdr, "IDR", locale) : b.priceUnavailable}
            </dd>
          </div>
        </dl>
        <p className="mt-3 text-sm text-muted">{b.planPerServerNote}</p>
        <p className="mt-1 text-sm text-muted">{b.providerNote}</p>
        {providerId && (
          <p className="mt-1 text-sm text-muted">{fmt(b.providerLabel, { provider: providerId })}</p>
        )}

        {!billingConfigured ? (
          <div className="mt-4 border-t border-edge pt-4">
            <p className="text-sm font-semibold text-fg">{b.notConfiguredTitle}</p>
            <p className="mt-1 text-sm text-muted">{b.notConfiguredBody}</p>
            <button type="button" disabled className={`${primaryBtnCls} mt-4`} aria-disabled="true">
              {b.checkoutButton}
            </button>
          </div>
        ) : (
          <div className="mt-4 border-t border-edge pt-4">
            <button
              type="button"
              onClick={startCheckout}
              disabled={checkingOut || priceIdr === null}
              aria-busy={checkingOut}
              className={primaryBtnCls}
            >
              {checkingOut ? b.checkoutLoading : b.checkoutButton}
            </button>
            {checkoutError && (
              <p role="alert" className="mt-3 text-sm text-red-400">
                {checkoutError}
              </p>
            )}
          </div>
        )}
      </section>

      {/* Perbandingan batas fitur Free vs VIP dari katalog nyata */}
      <section aria-label={b.comparisonTitle}>
        <h2 className="text-base font-semibold text-fg">{b.comparisonTitle}</h2>
        <div className="mt-3 overflow-x-auto rounded-xl border border-edge bg-panel">
          <table className="w-full min-w-[420px] text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
                <th scope="col" className="px-4 py-2.5 font-medium">{b.colFeature}</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">{b.colFree}</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">{b.colVip}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {featureCodes.map((code) => (
                <tr key={code}>
                  <td className="px-4 py-2.5 text-fg">{b.features[code]}</td>
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
      </section>

      {/* Riwayat pesanan */}
      <section aria-label={b.ordersTitle}>
        <h2 className="text-base font-semibold text-fg">{b.ordersTitle}</h2>
        {orders.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{b.ordersEmpty}</p>
        ) : (
          <div className="mt-3 overflow-x-auto rounded-xl border border-edge bg-panel">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead>
                <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colOrder}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colPlan}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colAmount}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colStatus}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colDate}</th>
                  <th scope="col" className="px-4 py-2.5 font-medium">{b.colDetail}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-edge">
                {orders.map((o) => (
                  <tr key={o.order_ref}>
                    <td className="px-4 py-2.5 font-mono text-xs text-fg">
                      {shortRef(o.order_ref)}
                    </td>
                    <td className="px-4 py-2.5 text-fg">{planText(o.plan_id)}</td>
                    <td className="px-4 py-2.5 text-fg">
                      {formatHarga(o.amount_idr, o.currency, locale)}
                    </td>
                    <td className="px-4 py-2.5">
                      <span
                        className={`rounded-full px-2.5 py-1 text-xs font-semibold ${statusBadgeCls(o.status)}`}
                      >
                        {orderStatusText(o.status)}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-4 py-2.5 text-muted">
                      {formatTanggal(o.created_at, locale)}
                    </td>
                    <td className="px-4 py-2.5">
                      <Link
                        href={`/dashboard/${guildId}/billing/orders/${o.order_ref}`}
                        className="inline-flex min-h-[44px] items-center font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                        aria-label={`${b.viewDetail}: ${o.order_ref}`}
                      >
                        {b.viewDetail}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function shortRef(ref: string): string {
  return ref.length > 12 ? `${ref.slice(0, 12)}...` : ref;
}

function formatHarga(amount: number, currency: string, locale: string): string {
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: currency || "IDR",
      maximumFractionDigits: 0,
    }).format(amount);
  } catch {
    return `${amount} ${currency || "IDR"}`;
  }
}

function formatTanggal(iso: string | null, locale: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "medium", timeStyle: "short" });
}
