"use client";

import { useState } from "react";
import Link from "next/link";
import type { SnapshotChannel } from "@/lib/db";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface QuotaInfo {
  feature: string;
  used: number;
  limit: number;
  vipLimit: number;
  tier: string;
}

/** Parse badan 409 { error: "quota_exceeded", feature, used, limit, vip_limit, tier }. */
function parseQuotaPayload(data: unknown): QuotaInfo | null {
  if (!data || typeof data !== "object") return null;
  const d = data as Record<string, unknown>;
  if (d.error !== "quota_exceeded") return null;
  const used = Number(d.used);
  const limit = Number(d.limit);
  const vipLimit = Number(d.vip_limit);
  if (!Number.isFinite(used) || !Number.isFinite(limit) || !Number.isFinite(vipLimit)) {
    return null;
  }
  return {
    feature: typeof d.feature === "string" ? d.feature : "giveaways_active",
    used,
    limit,
    vipLimit,
    tier: typeof d.tier === "string" ? d.tier : "free",
  };
}

interface Active {
  id: number;
  channel_id: string;
  prize: string;
  winners: number;
  ends_at: string;
  participants: number;
}

interface ReqRow {
  id: number;
  prize: string;
  winners: number;
  duration_minutes: number;
  status: string;
  note: string;
  created_at: string;
}

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

function formatEnds(iso: string, locale: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "-" : d.toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function GiveawayManager({
  guildId,
  channels,
  initialActive,
  initialRequests,
  tier,
  limit,
  vipLimit,
}: {
  guildId: string;
  channels: SnapshotChannel[];
  initialActive: Active[];
  initialRequests: ReqRow[];
  tier: "free" | "vip";
  limit: number;
  vipLimit: number;
}) {
  const { lang, dict } = useI18n();
  const g = dict.guild.giveaway;
  const q = dict.guild.common.quota;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [active, setActive] = useState<Active[]>(initialActive);
  const [requests, setRequests] = useState<ReqRow[]>(initialRequests);
  // Error khusus refresh pasca-mutasi: list lama tetap tampil + peringatan.
  const [refreshError, setRefreshError] = useState(false);
  const [channelId, setChannelId] = useState("");
  const [prize, setPrize] = useState("");
  const [winners, setWinners] = useState(1);
  const [duration, setDuration] = useState(60);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  // Guard klik ganda: satu request buat-giveaway dalam satu waktu.
  const [saving, setSaving] = useState(false);
  // Kuota otoritatif dari respons 409 terakhir (mengalahkan hitungan lokal).
  const [serverQuota, setServerQuota] = useState<QuotaInfo | null>(null);

  // used giveaway = request pending + giveaway aktif, persis seperti
  // hitungan GET/POST route giveaways (pending dashboard + aktif snapshot).
  const used =
    requests.filter((r) => r.status === "pending").length + active.length;
  const displayQuota: QuotaInfo | null =
    serverQuota ??
    (used >= limit
      ? { feature: "giveaways_active", used, limit, vipLimit, tier }
      : null);
  const quotaReached = displayQuota !== null;

  const tierLabel = (t: string) =>
    t === "vip" ? dict.billing.tierVip : dict.billing.tierFree;
  const featureLabel = (code: string) =>
    (dict.billing.features as Record<string, string>)[code] ??
    dict.billing.features.giveaways_active;

  function renderQuotaBox(info: QuotaInfo) {
    return (
      <div
        role="alert"
        className="mb-4 rounded-xl border border-yellow-500/30 bg-yellow-500/10 p-4"
      >
        <p className="text-sm font-semibold text-fg">{q.title}</p>
        <p className="mt-1 text-sm text-muted">
          {fmt(q.body, {
            feature: featureLabel(info.feature),
            used: info.used,
            limit: info.limit,
            tier: tierLabel(info.tier),
          })}
        </p>
        <p className="mt-1 text-sm text-muted">
          {fmt(q.vipHint, { vipLimit: info.vipLimit })}
        </p>
        {info.used > info.limit && (
          <p className="mt-1 text-sm text-muted">{q.downgradeNote}</p>
        )}
        <Link
          href={`/dashboard/${guildId}/billing`}
          className="mt-3 inline-flex min-h-[44px] items-center rounded-lg bg-brand px-4 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-brand"
        >
          {q.upgradeCta}
        </Link>
      </div>
    );
  }

  const textChannels = channels.filter((c) => c.type === 0 || c.type === 5);

  // Refresh TANPA mengganti list dengan teks "loading": data lama tetap
  // tampil (tidak berkedip); bila gagal, tampil peringatan di atas list.
  async function reload() {
    setRefreshError(false);
    try {
      const res = await fetch(`/api/guilds/${guildId}/giveaways`);
      if (!res.ok) throw new Error("http");
      const data = await res.json();
      setActive(data.active ?? []);
      setRequests(data.requests ?? []);
      setServerQuota(null);
    } catch {
      setRefreshError(true);
    }
  }

  async function create() {
    if (saving) return;
    setSaving(true);
    setStatus("idle");
    try {
      // Clamp: input angka yang dikosongkan user jadi 0/NaN (Number("")) —
      // tanpa ini payload winners:0/duration:0 bisa terkirim.
      const res = await fetch(`/api/guilds/${guildId}/giveaways`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          channel_id: channelId,
          prize: prize.trim(),
          winners: Math.max(1, Math.floor(winners) || 1),
          duration_minutes: Math.max(1, Math.floor(duration) || 1),
        }),
      });
      if (res.ok) {
        setPrize("");
        setStatus("ok");
        reload();
      } else if (res.status === 409) {
        const quota = parseQuotaPayload(await res.json().catch(() => null));
        if (quota) {
          setServerQuota(quota);
          setStatus("idle");
        } else {
          setStatus("error");
        }
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      {displayQuota && renderQuotaBox(displayQuota)}
      <div
        className={`rounded-xl border border-edge bg-panel p-5 ${quotaReached ? "opacity-60" : ""}`}
        aria-disabled={quotaReached || undefined}
      >
        <h2 className="text-sm font-semibold text-fg">{g.formTitle}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="gw-channel" className="text-xs font-medium text-muted">{g.channelLabel}</label>
            <select id="gw-channel" value={channelId} onChange={(e) => setChannelId(e.target.value)} disabled={quotaReached} className={`${inputCls} mt-1 w-full disabled:opacity-60`}>
              <option value="">{g.selectChannel}</option>
              {textChannels.map((c) => (
                <option key={c.id} value={c.id}>
                  # {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="gw-prize" className="text-xs font-medium text-muted">{g.prizeLabel}</label>
            <input
              id="gw-prize"
              value={prize}
              onChange={(e) => setPrize(e.target.value)}
              placeholder={g.prizePlaceholder}
              maxLength={100}
              disabled={quotaReached}
              className={`${inputCls} mt-1 w-full disabled:opacity-60`}
            />
          </div>
          <div>
            <label htmlFor="gw-winners" className="text-xs font-medium text-muted">{g.winnersLabel}</label>
            <input
              id="gw-winners"
              type="number"
              min={1}
              max={25}
              value={winners}
              onChange={(e) => setWinners(Number(e.target.value))}
              disabled={quotaReached}
              className={`${inputCls} mt-1 w-full disabled:opacity-60`}
            />
          </div>
          <div>
            <label htmlFor="gw-duration" className="text-xs font-medium text-muted">{g.durationLabel}</label>
            <input
              id="gw-duration"
              type="number"
              min={1}
              max={10080}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              disabled={quotaReached}
              className={`${inputCls} mt-1 w-full disabled:opacity-60`}
            />
          </div>
        </div>
        <button
          onClick={create}
          disabled={!channelId || !prize.trim() || saving || quotaReached}
          className="mt-4 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {saving ? dict.settings.saving : g.create}
        </button>
        {status === "ok" && <p role="status" className="mt-2 text-sm text-brand">{g.createOk}</p>}
        {status === "error" && <p role="alert" className="mt-2 text-sm text-red-400">{g.createError}</p>}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-fg">{g.activeTitle}</h2>
        {refreshError && (
          <p role="alert" className="mt-3 text-sm text-red-400">{dict.common.refreshError}</p>
        )}
        {active.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{g.emptyActive}</p>
        ) : (
          <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
            {active.map((gv) => (
              <li key={gv.id} className="px-5 py-3">
                <p className="text-sm font-medium text-fg">{gv.prize}</p>
                <p className="mt-1 font-mono text-xs text-muted">
                  {fmt(g.activeLine, {
                    participants: gv.participants,
                    winners: gv.winners,
                    endsAt: formatEnds(gv.ends_at, locale),
                  })}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {requests.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-fg">{g.historyTitle}</h2>
          <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
            {requests.map((r) => {
              const reqStatus =
                r.status === "pending" ? g.statusPending
                : r.status === "done" ? g.statusDone
                : fmt(g.statusFailed, { note: r.note || "-" });
              return (
                <li key={r.id} className="px-5 py-3">
                  <p className="text-sm font-medium text-fg">{r.prize}</p>
                  <p className="mt-1 font-mono text-xs text-muted">
                    {fmt(g.requestLine, { status: reqStatus, duration: r.duration_minutes, winners: r.winners })}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
