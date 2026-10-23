"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useI18n } from "@/components/I18nProvider";
import { fmt, type Dict, type Lang } from "@/lib/i18n/client";

export interface OrderDetailView {
  order_ref: string;
  plan_id: string;
  amount_idr: number;
  currency: string;
  status: string;
  provider: string | null;
  provider_redirect_url: string | null;
  created_at: string | null;
  expires_at: string | null;
  paid_at: string | null;
  entitlement_applied_at: string | null;
}

interface OrderStatusPollerProps {
  guildId: string;
  orderRef: string;
  initialStatus: string;
  initialOrder: OrderDetailView;
  dict: Dict;
  lang: Lang;
}

const TERMINAL_STATUSES = new Set([
  "paid",
  "failed",
  "expired",
  "cancelled",
  "refunded",
  "disputed",
]);

const POLL_MS = 4000;

const primaryBtnCls =
  "inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-5 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

const ghostBtnCls =
  "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-4 text-sm font-medium text-fg hover:border-brand hover:text-brand focus-visible:outline-2 focus-visible:outline-brand";

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

function pickOrder(data: unknown): Record<string, unknown> | null {
  if (!data || typeof data !== "object") return null;
  const obj = data as Record<string, unknown>;
  if (typeof obj.order_ref === "string" && typeof obj.status === "string") return obj;
  const nested = obj.order;
  if (nested && typeof nested === "object") {
    const n = nested as Record<string, unknown>;
    if (typeof n.order_ref === "string" && typeof n.status === "string") return n;
  }
  return null;
}

function toView(raw: Record<string, unknown>, fallback: OrderDetailView): OrderDetailView {
  const str = (v: unknown, fb: string | null): string | null =>
    typeof v === "string" ? v : fb;
  const num = (v: unknown, fb: number): number =>
    typeof v === "number" && Number.isFinite(v) ? v : fb;
  return {
    order_ref: str(raw.order_ref, fallback.order_ref) ?? fallback.order_ref,
    plan_id: str(raw.plan_id, fallback.plan_id) ?? fallback.plan_id,
    amount_idr: num(raw.amount_idr, fallback.amount_idr),
    currency: str(raw.currency, fallback.currency) ?? fallback.currency,
    status: str(raw.status, fallback.status) ?? fallback.status,
    provider: str(raw.provider, fallback.provider),
    provider_redirect_url: str(
      raw.provider_redirect_url,
      fallback.provider_redirect_url,
    ),
    created_at: str(raw.created_at, fallback.created_at) ?? fallback.created_at,
    expires_at: str(raw.expires_at, fallback.expires_at),
    paid_at: str(raw.paid_at, fallback.paid_at),
    entitlement_applied_at: str(
      raw.entitlement_applied_at,
      fallback.entitlement_applied_at,
    ),
  };
}

/**
 * Poller status pesanan: memeriksa GET detail pesanan tiap 4 detik selama
 * status masih created/pending, dan berhenti sendiri pada status terminal.
 * Status selalu ditampilkan sebagai label teks (bukan hanya warna), dan
 * instruksi per status berasal dari kamus billing.orderDetail.
 *
 * dict/lang diteruskan server lewat props sebagai nilai awal; nilai live
 * dari useI18n() dipakai agar pergantian bahasa tetap sinkron.
 */
export default function OrderStatusPoller({
  guildId,
  orderRef,
  initialStatus,
  initialOrder,
  dict: initialDict,
  lang: initialLang,
}: OrderStatusPollerProps) {
  const { dict: liveDict, lang: liveLang } = useI18n();
  const dict = liveDict ?? initialDict;
  const lang = liveLang ?? initialLang;
  const b = dict.billing;
  const od = b.orderDetail;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [order, setOrder] = useState<OrderDetailView>({
    ...initialOrder,
    status: initialStatus,
  });
  const [lastChecked, setLastChecked] = useState<string | null>(null);
  const [checkError, setCheckError] = useState(false);

  const status = order.status;
  const isTerminal = TERMINAL_STATUSES.has(status);

  // Polling bergantung pada status: effect berhenti sendiri (cleanup)
  // begitu status berubah menjadi terminal, karena cabang terminal di
  // bawah tidak memasang interval sama sekali.
  useEffect(() => {
    if (TERMINAL_STATUSES.has(status)) return;
    let alive = true;

    async function check() {
      try {
        const res = await fetch(
          `/api/guilds/${guildId}/billing/orders/${encodeURIComponent(orderRef)}`,
        );
        if (!res.ok) throw new Error("http");
        const data: unknown = await res.json();
        const raw = pickOrder(data);
        if (!alive) return;
        if (raw) {
          setOrder((prev) => toView(raw, prev));
          setCheckError(false);
        } else {
          setCheckError(true);
        }
        setLastChecked(new Date().toISOString());
      } catch {
        if (alive) setCheckError(true);
      }
    }

    void check();
    const timer = setInterval(() => {
      void check();
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [guildId, orderRef, status]);

  const statusText = (s: string): string => {
    const map = b.orderStatus as Record<string, string>;
    return map[s] ?? b.orderStatus.unknown;
  };

  const planText =
    order.plan_id === "vip_monthly" || order.plan_id === "vip_30d"
      ? b.planVip30d
      : order.plan_id;
  const ins = od.instructions;

  const instruction =
    status === "paid"
      ? { title: ins.paidTitle, body: ins.paidBody }
      : status === "failed"
        ? { title: ins.failedTitle, body: ins.failedBody }
        : status === "expired"
          ? { title: ins.expiredTitle, body: ins.expiredBody }
          : status === "cancelled"
            ? { title: ins.cancelledTitle, body: ins.cancelledBody }
            : status === "refunded"
              ? { title: ins.refundedTitle, body: ins.refundedBody }
              : status === "disputed"
                ? { title: ins.disputedTitle, body: ins.disputedBody }
                : { title: ins.pendingTitle, body: ins.pendingBody };

  const showNewTransaction =
    status === "failed" || status === "expired" || status === "cancelled";
  const showContinuePayment =
    !isTerminal && Boolean(order.provider_redirect_url);

  return (
    <div className="space-y-6">
      <section
        aria-label={od.title}
        className="rounded-2xl border border-edge bg-panel p-5 sm:p-7"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <h2 className="text-lg font-bold text-fg">{od.title}</h2>
          <span
            role="status"
            className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeCls(status)}`}
          >
            {statusText(status)}
          </span>
        </div>

        <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs text-muted">{od.orderRefLabel}</dt>
            <dd className="mt-0.5 font-mono text-xs font-semibold break-all text-fg">
              {order.order_ref}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{od.planLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{planText}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{od.amountLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">
              {formatHarga(order.amount_idr, order.currency, locale)}
            </dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{od.statusLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">{statusText(status)}</dd>
          </div>
          <div>
            <dt className="text-xs text-muted">{od.createdLabel}</dt>
            <dd className="mt-0.5 font-semibold text-fg">
              {formatTanggal(order.created_at, locale)}
            </dd>
          </div>
          {order.expires_at && (
            <div>
              <dt className="text-xs text-muted">{od.expiresLabel}</dt>
              <dd className="mt-0.5 font-semibold text-fg">
                {formatTanggal(order.expires_at, locale)}
              </dd>
            </div>
          )}
          {order.paid_at && (
            <div>
              <dt className="text-xs text-muted">{od.paidLabel}</dt>
              <dd className="mt-0.5 font-semibold text-fg">
                {formatTanggal(order.paid_at, locale)}
              </dd>
            </div>
          )}
          {order.entitlement_applied_at && (
            <div>
              <dt className="text-xs text-muted">{od.appliedLabel}</dt>
              <dd className="mt-0.5 font-semibold text-fg">
                {formatTanggal(order.entitlement_applied_at, locale)}
              </dd>
            </div>
          )}
          {order.provider && (
            <div>
              <dt className="text-xs text-muted">{od.providerLabel}</dt>
              <dd className="mt-0.5 font-semibold text-fg">{order.provider}</dd>
            </div>
          )}
        </dl>

        {!isTerminal && (
          <p className="mt-4 text-sm text-muted">{od.autoUpdateNote}</p>
        )}
        {lastChecked && (
          <p className="mt-1 text-xs text-muted">
            {fmt(od.lastChecked, { time: formatTanggal(lastChecked, locale) })}
          </p>
        )}
        {checkError && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {od.checkError}
          </p>
        )}
      </section>

      <section
        aria-label={instruction.title}
        className="rounded-2xl border border-edge bg-panel p-5 sm:p-7"
      >
        <h2 className="text-base font-bold text-fg">{instruction.title}</h2>
        <p className="mt-1 text-sm leading-relaxed text-muted">{instruction.body}</p>
        {status === "paid" && order.entitlement_applied_at && (
          <p className="mt-2 text-sm leading-relaxed text-muted">{ins.paidSyncNote}</p>
        )}
        <div className="mt-4 flex flex-wrap gap-2">
          {showContinuePayment && order.provider_redirect_url && (
            <a href={order.provider_redirect_url} className={primaryBtnCls}>
              {b.continuePayment}
            </a>
          )}
          {showNewTransaction && (
            <Link href={`/dashboard/${guildId}/billing`} className={primaryBtnCls}>
              {od.newTransaction}
            </Link>
          )}
          <Link href={`/dashboard/${guildId}/billing`} className={ghostBtnCls}>
            {b.backToBilling}
          </Link>
          <Link href={`/dashboard/${guildId}`} className={ghostBtnCls}>
            {b.backToDashboard}
          </Link>
        </div>
      </section>
    </div>
  );
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
