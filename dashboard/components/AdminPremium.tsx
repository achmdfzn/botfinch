"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useI18n } from "@/components/I18nProvider";
import { fmt, type Dict, type Lang } from "@/lib/i18n/client";

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

const primaryBtnCls =
  "inline-flex min-h-[44px] items-center rounded-lg bg-brand px-4 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand";

const ghostBtnCls =
  "inline-flex min-h-[44px] items-center rounded-lg border border-edge px-4 text-sm font-medium text-fg hover:border-brand hover:text-brand disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand";

interface EntitlementView {
  guild_id: string;
  name: string | null;
  tier: string;
  status: string;
  source: string | null;
  starts_at: string | null;
  expires_at: string | null;
  granted_by: string | null;
  note: string | null;
  bot_present: boolean;
  updated_at: string | null;
}

interface AuditEntry {
  id: number;
  guild_id: string;
  actor_id: string | null;
  action: string;
  tier_before: string | null;
  tier_after: string | null;
  status_before: string | null;
  status_after: string | null;
  expires_before: string | null;
  expires_after: string | null;
  reason: string | null;
  created_at: string;
}

type AdminAction = "grant" | "extend" | "revoke";

/**
 * Panel admin Premium (khusus owner bot; guard server ada di halaman
 * app/dashboard/admin/premium). Semua mutasi lewat API admin entitlement:
 * komponen ini TIDAK pernah mengirim tier/expires_at/isOwner, hanya
 * guild_id, action, duration_days, dan reason.
 *
 * dict/lang diteruskan server lewat props sebagai nilai awal; nilai live
 * dari useI18n() dipakai agar pergantian bahasa tanpa reload tetap sinkron.
 */
export default function AdminPremium({
  dict: initialDict,
  lang: initialLang,
}: {
  dict: Dict;
  lang: Lang;
}) {
  const { dict: liveDict, lang: liveLang } = useI18n();
  const dict = liveDict ?? initialDict;
  const lang = liveLang ?? initialLang;
  const p = dict.premium;
  const a = p.admin;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [query, setQuery] = useState("");
  const [rows, setRows] = useState<EntitlementView[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [guildIdInput, setGuildIdInput] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<EntitlementView | null>(null);
  const [audit, setAudit] = useState<AuditEntry[]>([]);
  const [auditError, setAuditError] = useState(false);
  const [durationDays, setDurationDays] = useState("");
  const [reason, setReason] = useState("");
  const [busyAction, setBusyAction] = useState<AdminAction | null>(null);
  const [actionStatus, setActionStatus] = useState<"idle" | "ok" | "error">("idle");

  async function loadList(q: string) {
    const res = await fetch(
      q.trim()
        ? `/api/admin/entitlements?q=${encodeURIComponent(q.trim())}`
        : "/api/admin/entitlements",
    );
    if (!res.ok) throw new Error("http");
    const data = await res.json();
    setRows((data.entitlements ?? []) as EntitlementView[]);
  }

  async function loadDetail(guildId: string) {
    try {
      const res = await fetch(
        `/api/admin/entitlements?guild_id=${encodeURIComponent(guildId)}`,
      );
      if (!res.ok) throw new Error("http");
      const data = await res.json();
      setSelected((data.entitlement ?? null) as EntitlementView | null);
      setAudit((data.audit ?? []) as AuditEntry[]);
      setAuditError(false);
    } catch {
      setAuditError(true);
    }
  }

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await fetch("/api/admin/entitlements");
        if (!res.ok) throw new Error("http");
        const data = await res.json();
        if (alive) setRows((data.entitlements ?? []) as EntitlementView[]);
      } catch {
        if (alive) setLoadError(true);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  async function search(e: FormEvent) {
    e.preventDefault();
    setLoadError(false);
    try {
      await loadList(query);
    } catch {
      setLoadError(true);
    }
  }

  function selectGuild(guildId: string) {
    const id = guildId.trim();
    if (!id) return;
    setSelectedId(id);
    setGuildIdInput(id);
    setActionStatus("idle");
    void loadDetail(id);
  }

  async function runAction(action: AdminAction) {
    if (!selectedId || busyAction) return;
    const trimmedDuration = durationDays.trim();
    const durationNum = trimmedDuration === "" ? null : Number(trimmedDuration);
    // Extend wajib punya durasi valid; grant boleh kosong (permanen).
    if (action === "extend" && (durationNum === null || !Number.isFinite(durationNum) || durationNum <= 0)) {
      setActionStatus("error");
      return;
    }
    if (
      durationNum !== null &&
      (!Number.isFinite(durationNum) || durationNum <= 0)
    ) {
      setActionStatus("error");
      return;
    }
    if (action === "revoke" && !confirm(fmt(a.confirmRevoke, { id: selectedId }))) return;
    setBusyAction(action);
    setActionStatus("idle");
    try {
      const res = await fetch("/api/admin/entitlements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          guild_id: selectedId,
          action,
          duration_days: action === "revoke" ? null : durationNum,
          reason: reason.trim(),
        }),
      });
      if (!res.ok) throw new Error("http");
      setActionStatus("ok");
      setReason("");
      try {
        await loadList(query);
      } catch {
        setLoadError(true);
      }
      await loadDetail(selectedId);
    } catch {
      setActionStatus("error");
    } finally {
      setBusyAction(null);
    }
  }

  const tierText = (tier: string) => (tier === "vip" ? p.tierVip : p.tierFree);
  const statusText = (status: string | null) =>
    status === "active"
      ? p.statusActive
      : status === "revoked"
        ? p.statusRevoked
        : status === "expired"
          ? p.statusExpired
          : (status ?? "-");
  const actionText = (action: string) =>
    action === "grant" ? a.grant : action === "extend" ? a.extend : action === "revoke" ? a.revoke : action;
  const expiryText = (e: EntitlementView) =>
    e.expires_at
      ? formatTanggal(e.expires_at, locale)
      : e.tier === "vip"
        ? p.permanent
        : "-";
  const auditValue = (v: string | null, kind: "tier" | "status" | "expires") => {
    if (!v) return "-";
    if (kind === "tier") return tierText(v);
    if (kind === "status") return statusText(v);
    return formatTanggal(v, locale);
  };

  return (
    <div>
      {/* Pencarian + pilih guild manual */}
      <div className="rounded-xl border border-edge bg-panel p-5">
        <form onSubmit={search} className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="ap-search" className="text-xs font-medium text-muted">
              {a.searchLabel}
            </label>
            <input
              id="ap-search"
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={a.searchPlaceholder}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
          <button type="submit" className={primaryBtnCls}>
            {a.searchButton}
          </button>
        </form>

        <div className="mt-4 flex flex-col gap-3 border-t border-edge pt-4 sm:flex-row sm:items-end">
          <div className="flex-1">
            <label htmlFor="ap-guild-id" className="text-xs font-medium text-muted">
              {a.guildIdLabel}
            </label>
            <input
              id="ap-guild-id"
              type="text"
              inputMode="numeric"
              value={guildIdInput}
              onChange={(e) => setGuildIdInput(e.target.value)}
              placeholder={a.guildIdPlaceholder}
              className={`${inputCls} mt-1 w-full`}
            />
            <p className="mt-1 text-xs text-muted">{a.guildIdHint}</p>
          </div>
          <button
            type="button"
            onClick={() => selectGuild(guildIdInput)}
            disabled={!guildIdInput.trim()}
            className={ghostBtnCls}
          >
            {a.selectGuildButton}
          </button>
        </div>
      </div>

      {/* Daftar entitlement */}
      <h2 className="mt-6 text-sm font-semibold text-fg">{a.listTitle}</h2>
      {loading ? (
        <p className="mt-3 text-sm text-muted">{dict.common.loading}</p>
      ) : loadError ? (
        <p role="alert" className="mt-3 text-sm text-red-400">{a.listError}</p>
      ) : rows.length === 0 ? (
        <p className="mt-3 text-sm text-muted">{a.listEmpty}</p>
      ) : (
        <div className="mt-3 overflow-x-auto rounded-xl border border-edge bg-panel">
          <table className="w-full min-w-[760px] text-left text-sm">
            <thead>
              <tr className="border-b border-edge text-xs uppercase tracking-wider text-muted">
                <th scope="col" className="px-5 py-3 font-medium">{a.colGuild}</th>
                <th scope="col" className="px-5 py-3 font-medium">{a.colTier}</th>
                <th scope="col" className="px-5 py-3 font-medium">{a.colStatus}</th>
                <th scope="col" className="px-5 py-3 font-medium">{a.colExpires}</th>
                <th scope="col" className="px-5 py-3 font-medium">{a.colSource}</th>
                <th scope="col" className="px-5 py-3 font-medium">{a.colUpdated}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-edge">
              {rows.map((e) => (
                <tr
                  key={e.guild_id}
                  onClick={() => selectGuild(e.guild_id)}
                  className={`cursor-pointer align-top hover:bg-edge ${
                    selectedId === e.guild_id ? "bg-brand/10" : ""
                  }`}
                >
                  <td className="px-5 py-3">
                    <span className="font-medium text-fg">{e.name ?? a.unknownName}</span>
                    <span className="block font-mono text-xs text-muted">{e.guild_id}</span>
                  </td>
                  <td className="px-5 py-3">
                    <span
                      className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                        e.tier === "vip" ? "bg-brand/15 text-brand" : "bg-edge text-muted"
                      }`}
                    >
                      {tierText(e.tier)}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-fg">{statusText(e.status)}</td>
                  <td className="whitespace-nowrap px-5 py-3 text-muted">{expiryText(e)}</td>
                  <td className="px-5 py-3 text-muted">{e.source ?? "-"}</td>
                  <td className="whitespace-nowrap px-5 py-3 font-mono text-xs text-muted">
                    {e.updated_at ? formatTanggal(e.updated_at, locale) : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Panel aksi untuk guild terpilih */}
      <div className="mt-6 rounded-xl border border-edge bg-panel p-5">
        <h2 className="text-sm font-semibold text-fg">{a.actionsTitle}</h2>
        {!selectedId ? (
          <p className="mt-2 text-sm text-muted">{a.noSelection}</p>
        ) : (
          <>
            <p className="mt-2 text-sm text-fg">
              {a.selectedTitle}:{" "}
              <span className="font-semibold">{selected?.name ?? selectedId}</span>
            </p>
            <p className="font-mono text-xs text-muted">
              {fmt(a.selectedGuild, { id: selectedId })}
            </p>
            {selected && (
              <p className="mt-1 text-sm text-muted">
                {tierText(selected.tier)} · {statusText(selected.status)} · {expiryText(selected)}
              </p>
            )}

            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <div>
                <label htmlFor="ap-duration" className="text-xs font-medium text-muted">
                  {a.durationLabel}
                </label>
                <input
                  id="ap-duration"
                  type="number"
                  min={1}
                  value={durationDays}
                  onChange={(e) => setDurationDays(e.target.value)}
                  className={`${inputCls} mt-1 w-full`}
                />
                <p className="mt-1 text-xs text-muted">{a.durationHintGrant}</p>
                <p className="text-xs text-muted">{a.durationHintExtend}</p>
              </div>
              <div>
                <label htmlFor="ap-reason" className="text-xs font-medium text-muted">
                  {a.reasonLabel}
                </label>
                <input
                  id="ap-reason"
                  type="text"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder={a.reasonPlaceholder}
                  className={`${inputCls} mt-1 w-full`}
                />
              </div>
            </div>

            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => runAction("grant")}
                disabled={busyAction !== null}
                className={primaryBtnCls}
              >
                {a.grant}
              </button>
              <button
                type="button"
                onClick={() => runAction("extend")}
                disabled={busyAction !== null}
                className={ghostBtnCls}
              >
                {a.extend}
              </button>
              <button
                type="button"
                onClick={() => runAction("revoke")}
                disabled={busyAction !== null}
                className="inline-flex min-h-[44px] items-center rounded-lg border border-edge px-4 text-sm font-medium text-red-400 hover:bg-edge disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand"
              >
                {a.revoke}
              </button>
            </div>
            {actionStatus === "ok" && (
              <p role="status" className="mt-3 text-sm text-brand">{a.actionSuccess}</p>
            )}
            {actionStatus === "error" && (
              <p role="alert" className="mt-3 text-sm text-red-400">{a.actionError}</p>
            )}
          </>
        )}
      </div>

      {/* Riwayat audit guild terpilih */}
      {selectedId && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-fg">{a.auditTitle}</h2>
          {auditError ? (
            <p role="alert" className="mt-3 text-sm text-red-400">{a.auditError}</p>
          ) : audit.length === 0 ? (
            <p className="mt-3 text-sm text-muted">{a.auditEmpty}</p>
          ) : (
            <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
              {audit.map((entry) => (
                <li key={entry.id} className="px-5 py-4">
                  <p className="text-sm font-medium text-fg">
                    {actionText(entry.action)}{" "}
                    <span className="font-normal text-muted">
                      · {formatTanggal(entry.created_at, locale)} ·{" "}
                      {fmt(a.auditActor, { actor: entry.actor_id ?? "-" })}
                    </span>
                  </p>
                  <p className="mt-0.5 text-sm text-muted">
                    {fmt(a.auditTier, {
                      before: auditValue(entry.tier_before, "tier"),
                      after: auditValue(entry.tier_after, "tier"),
                    })}
                    {" · "}
                    {fmt(a.auditStatus, {
                      before: auditValue(entry.status_before, "status"),
                      after: auditValue(entry.status_after, "status"),
                    })}
                    {" · "}
                    {fmt(a.auditExpires, {
                      before: auditValue(entry.expires_before, "expires"),
                      after: auditValue(entry.expires_after, "expires"),
                    })}
                  </p>
                  {entry.reason && (
                    <p className="mt-0.5 text-sm text-muted">
                      {fmt(a.auditReason, { reason: entry.reason })}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function formatTanggal(iso: string, locale: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(locale, { dateStyle: "short", timeStyle: "short" });
}
