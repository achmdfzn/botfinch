"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { SnapshotChannel } from "@/lib/db";
import Toggle from "./Toggle";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

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
    feature: typeof d.feature === "string" ? d.feature : "announcements_active",
    used,
    limit,
    vipLimit,
    tier: typeof d.tier === "string" ? d.tier : "free",
  };
}

interface Announcement {
  id: number;
  channel_id: string;
  message: string;
  run_at: string | null;
  interval_minutes: number | null;
  enabled: boolean;
  last_sent_at: string | null;
}

export default function AnnouncementsManager({
  guildId,
  channels,
  tier,
  limit,
  vipLimit,
}: {
  guildId: string;
  channels: SnapshotChannel[];
  tier: "free" | "vip";
  limit: number;
  vipLimit: number;
}) {
  const { lang, dict } = useI18n();
  const g = dict.guild.pengumuman;
  const q = dict.guild.common.quota;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [rows, setRows] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState(false);
  // Error khusus refresh pasca-mutasi: list lama tetap tampil + peringatan,
  // tidak diganti pesan error penuh (data basi lebih baik dari list hilang).
  const [refreshError, setRefreshError] = useState(false);
  const [channelId, setChannelId] = useState("");
  const [message, setMessage] = useState("");
  const [mode, setMode] = useState<"sekali" | "berulang">("sekali");
  const [runAt, setRunAt] = useState("");
  const [intervalMin, setIntervalMin] = useState("60");
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  // Guard klik ganda per baris saat toggle enabled.
  const [busyRows, setBusyRows] = useState<ReadonlySet<number>>(new Set());
  // Kuota otoritatif dari respons 409 terakhir (POST tambah / PUT toggle).
  const [serverQuota, setServerQuota] = useState<QuotaInfo | null>(null);

  // Kuota pengumuman dihitung dari yang enabled saja (sama seperti route).
  const used = rows.filter((r) => r.enabled).length;
  const displayQuota: QuotaInfo | null =
    serverQuota ??
    (used >= limit
      ? { feature: "announcements_active", used, limit, vipLimit, tier }
      : null);
  const quotaReached = displayQuota !== null;

  const tierLabel = (t: string) =>
    t === "vip" ? dict.billing.tierVip : dict.billing.tierFree;
  const featureLabel = (code: string) =>
    (dict.billing.features as Record<string, string>)[code] ??
    dict.billing.features.announcements_active;

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

  // Refresh list TANPA mengganti dengan teks "loading": list lama tetap
  // tampil (tidak berkedip); bila refresh gagal setelah mutasi sukses,
  // list lama dipertahankan dan pesan error ditampilkan.
  async function reload() {
    setRefreshError(false);
    try {
      const res = await fetch(`/api/guilds/${guildId}/announcements`);
      if (!res.ok) throw new Error("http");
      const data = await res.json();
      setRows(data.announcements ?? []);
      setServerQuota(null);
    } catch {
      setRefreshError(true);
    }
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch(`/api/guilds/${guildId}/announcements`);
        if (alive) {
          if (res.ok) {
            const data = await res.json();
            setRows(data.announcements ?? []);
          } else {
            setFetchError(true);
          }
        }
      } catch {
        if (alive) setFetchError(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [guildId]);

  // Hanya channel teks yang bisa menerima kiriman (voice/stage tidak).
  const textChannels = channels.filter((c) => c.type === 0 || c.type === 5);
  const channelName = (id: string) => channels.find((c) => c.id === id)?.name ?? id;

  const intervalNum = Number(intervalMin);
  const canAdd =
    channelId &&
    message.trim().length > 0 &&
    !saving &&
    !quotaReached &&
    (mode === "berulang"
      ? Number.isInteger(intervalNum) && intervalNum >= 5 && intervalNum <= 43200
      : runAt.length > 0);

  async function add() {
    if (!canAdd) return;
    // Sekali kirim: run_at harus di masa depan. Pengecekan Date.now() di sini
    // (event handler), bukan di canAdd — react-hooks/purity melarang nilai
    // tak murni saat render. Tanggal lampau ditolak dengan pesan error.
    if (mode !== "berulang" && (Number.isNaN(Date.parse(runAt)) || Date.parse(runAt) <= Date.now())) {
      setStatus("error");
      return;
    }
    setStatus("idle");
    setSaving(true);
    try {
      const body: Record<string, unknown> = {
        channel_id: channelId,
        message: message.trim(),
      };
      if (mode === "sekali") {
        const d = new Date(runAt);
        if (Number.isNaN(d.getTime())) {
          setStatus("error");
          setSaving(false);
          return;
        }
        body.run_at = d.toISOString();
        body.interval_minutes = null;
      } else {
        body.run_at = null;
        body.interval_minutes = intervalNum;
      }
      const res = await fetch(`/api/guilds/${guildId}/announcements`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setChannelId("");
        setMessage("");
        setRunAt("");
        setIntervalMin("60");
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

  async function toggleRow(a: Announcement) {
    if (busyRows.has(a.id)) return;
    setBusyRows((prev) => new Set(prev).add(a.id));
    try {
      const res = await fetch(`/api/guilds/${guildId}/announcements/${a.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !a.enabled }),
      });
      // Bentuk error kuota seragam (409 quota_exceeded): tampilkan kotak
      // kuota dengan angka DARI RESPONS, bukan pesan error generik.
      const quota =
        res.status === 409
          ? parseQuotaPayload(await res.json().catch(() => null))
          : null;
      // Selalu sinkron ulang ke kebenaran server — juga saat gagal,
      // agar toggle tak macet di posisi yang salah. reload() membersihkan
      // serverQuota, jadi kuota respons dipasang SETELAH reload selesai.
      await reload();
      if (quota) {
        setServerQuota(quota);
        setStatus("idle");
      } else if (!res.ok) {
        setStatus("error");
      }
    } catch {
      setStatus("error");
      reload();
    } finally {
      setBusyRows((prev) => {
        const next = new Set(prev);
        next.delete(a.id);
        return next;
      });
    }
  }

  async function remove(a: Announcement) {
    const preview = `${a.message.slice(0, 40)}${a.message.length > 40 ? "..." : ""}`;
    if (!confirm(fmt(g.confirmDelete, { preview }))) return;
    try {
      const res = await fetch(`/api/guilds/${guildId}/announcements/${a.id}`, { method: "DELETE" });
      if (res.ok) reload();
      else setStatus("error");
    } catch {
      setStatus("error");
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

        <div className="mt-3">
          <label htmlFor="an-channel" className="text-xs font-medium text-muted">{g.channelLabel}</label>
          <select
            id="an-channel"
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
            disabled={quotaReached}
            className={`${inputCls} mt-1 w-full disabled:opacity-60`}
          >
            <option value="">{g.selectChannel}</option>
            {textChannels.map((c) => (
              <option key={c.id} value={c.id}>
                #{c.name}
              </option>
            ))}
          </select>
          {textChannels.length === 0 && (
            <p className="mt-1 text-xs text-muted">{g.noChannelsHint}</p>
          )}
        </div>

        <div className="mt-3">
          <label htmlFor="an-msg" className="text-xs font-medium text-muted">{g.messageLabel}</label>
          <textarea
            id="an-msg"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder={g.messagePlaceholder}
            rows={3}
            disabled={quotaReached}
            className={`${inputCls} mt-1 w-full resize-y disabled:opacity-60`}
          />
        </div>

        <fieldset className="mt-3">
          <legend className="text-xs font-medium text-muted">{g.modeLabel}</legend>
          <div className="mt-1 flex gap-2">
            {(["sekali", "berulang"] as const).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                disabled={quotaReached}
                aria-pressed={mode === m}
                className={`rounded-lg px-4 py-2 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand min-h-[44px] ${
                  mode === m
                    ? "bg-brand text-ink"
                    : "border border-edge text-muted hover:bg-edge"
                }`}
              >
                {m === "sekali" ? g.modeOnce : g.modeRepeat}
              </button>
            ))}
          </div>
        </fieldset>

        {mode === "sekali" ? (
          <div className="mt-3">
            <label htmlFor="an-runat" className="text-xs font-medium text-muted">
              {g.runAtLabel}
            </label>
            <input
              id="an-runat"
              type="datetime-local"
              value={runAt}
              onChange={(e) => setRunAt(e.target.value)}
              disabled={quotaReached}
              className={`${inputCls} mt-1 w-full disabled:opacity-60`}
            />
          </div>
        ) : (
          <div className="mt-3">
            <label htmlFor="an-interval" className="text-xs font-medium text-muted">
              {g.intervalLabel}
            </label>
            <input
              id="an-interval"
              type="number"
              min={5}
              max={43200}
              value={intervalMin}
              onChange={(e) => setIntervalMin(e.target.value)}
              disabled={quotaReached}
              className={`${inputCls} mt-1 w-full disabled:opacity-60`}
            />
          </div>
        )}

        <button
          onClick={add}
          disabled={!canAdd}
          className="mt-4 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {saving ? g.saving : dict.common.add}
        </button>
        {status === "ok" && (
          <p role="status" className="mt-2 text-sm text-brand">
            {g.addOk}
          </p>
        )}
        {status === "error" && (
          <p role="alert" className="mt-2 text-sm text-red-400">
            {g.addError}
          </p>
        )}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-fg">{fmt(g.listTitle, { n: rows.length })}</h2>
        {loading ? (
          <p className="mt-3 text-sm text-muted">{dict.common.loading}</p>
        ) : rows.length === 0 ? (
          fetchError ? (
            <p className="mt-3 text-sm text-muted">{g.listError}</p>
          ) : (
            <p className="mt-3 text-sm text-muted">{g.listEmpty}</p>
          )
        ) : (
          <>
            {refreshError && (
              <p role="alert" className="mt-3 text-sm text-red-400">{dict.common.refreshError}</p>
            )}
            <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
              {rows.map((a) => (
              <li key={a.id} className="flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-center">
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm font-medium text-fg">{a.message}</p>
                  <p className="mt-0.5 font-mono text-xs text-muted">
                    #{channelName(a.channel_id)} ·{" "}
                    {a.interval_minutes
                      ? fmt(g.rowRepeat, { n: a.interval_minutes })
                      : fmt(g.rowOnce, { time: formatWaktu(a.run_at, locale) })}
                    {a.last_sent_at ? ` · ${fmt(g.rowSent, { time: formatWaktu(a.last_sent_at, locale) })}` : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <Toggle
                    checked={a.enabled}
                    onChange={() => toggleRow(a)}
                    label={fmt(g.toggleAria, { id: a.id })}
                    disabled={busyRows.has(a.id)}
                  />
                  <button
                    onClick={() => remove(a)}
                    className="rounded-lg border border-edge px-3 py-2 text-sm text-red-400 hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
                  >
                    {dict.common.remove}
                  </button>
                </div>
              </li>
            ))}
          </ul>
          </>
        )}
      </div>
    </div>
  );
}

function formatWaktu(iso: string | null, locale: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}
