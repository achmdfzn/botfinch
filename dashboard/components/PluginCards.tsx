"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import type { PluginGroup, PluginTab } from "@/lib/plugins";
import PluginTabs, { usePluginTabQuery } from "./PluginTabs";
import { fmt } from "@/lib/i18n/client";

export type { PluginTab };

/**
 * Katalog plugin ala MEE6: tab kategori (Semua | Esensial | Engagement & Fun |
 * Moderasi | Utilitas, state di query ?tab= agar bisa di-share) + grid kartu.
 * Tiap kartu: tile ikon (maks 1 emoji), nama, deskripsi orisinal Finch, badge
 * status, tombol "Aktifkan"/"Nonaktifkan" yang men-toggle via
 * PUT /api/guilds/[id]/settings (optimistik + rollback, alur ModuleToggles),
 * dan tautan Konfigurasi bila plugin punya halaman konfigurasi.
 * Plugin tanpa toggleKey tampil "selalu aktif" tanpa tombol toggle.
 */
export interface PluginCardData {
  id: string;
  emoji: string;
  group: PluginGroup;
  /** Key settings untuk toggle; null = tool tanpa toggle. */
  toggleKey: string | null;
  /** Path relatif ke /dashboard/[guildId]; "" = home (overview); null = tanpa tautan. */
  configure: string | null;
  name: string;
  desc: string;
}

interface Labels {
  tabAll: string;
  enable: string;
  disable: string;
  configure: string;
  statusActive: string;
  statusInactive: string;
  saving: string;
  toggleError: string;
  toggleOn: string;
  toggleOff: string;
  tablistLabel: string;
  alwaysOn: string;
  pluginCount: string;
  tabDesc: Record<PluginTab, string>;
}

interface Props {
  guildId: string;
  plugins: PluginCardData[];
  initial: Record<string, boolean>;
  /** Tab awal dari query ?tab= (link sidebar plugin tanpa halaman config). */
  initialTab: PluginTab;
  groupTitles: Record<PluginGroup, string>;
  labels: Labels;
}

export default function PluginCards({
  guildId,
  plugins,
  initial,
  initialTab,
  groupTitles,
  labels,
}: Props) {
  const [tab, setTab] = usePluginTabQuery(initialTab);
  const [values, setValues] = useState<Record<string, boolean>>(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);
  const router = useRouter();
  // Guard klik ganda: abaikan toggle yang request-nya masih berjalan
  // (optimistik + rollback; race dua PUT bisa membalik rollback).
  const inflight = useRef(new Set<string>());

  async function toggle(key: string, v: boolean) {
    if (inflight.current.has(key)) return;
    inflight.current.add(key);
    setError(false);
    setSaving(key);
    setValues((prev) => ({ ...prev, [key]: v }));
    try {
      const res = await fetch(`/api/guilds/${guildId}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [key]: v }),
      });
      if (!res.ok) throw new Error("http");
      // Segarkan data server (mis. hitungan "N dari M plugin aktif" di header)
      // — state kartu sudah optimistik, jadi refresh aman.
      router.refresh();
    } catch {
      setValues((prev) => ({ ...prev, [key]: !v }));
      setError(true);
    } finally {
      inflight.current.delete(key);
      setSaving(null);
    }
  }

  const tabLabel = (t: PluginTab): string => (t === "all" ? labels.tabAll : groupTitles[t]);
  const visible = plugins.filter((p) => tab === "all" || p.group === tab);

  return (
    <div>
      <PluginTabs tab={tab} onChange={setTab} tabLabel={tabLabel} tablistLabel={labels.tablistLabel} />

      {/* Judul kategori ala referensi: nama tab + jumlah + deskripsi singkat */}
      <div className="mb-5 mt-6">
        <h2 className="inline-block border-b-2 border-brand pb-1 text-lg font-bold text-fg">
          {tabLabel(tab)}
        </h2>
        <p className="mt-2 text-sm text-muted">
          {fmt(labels.pluginCount, { n: visible.length })} · {labels.tabDesc[tab]}
        </p>
      </div>

      {error && (
        <p
          role="alert"
          className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400"
        >
          {labels.toggleError}
        </p>
      )}

      <div
        role="tabpanel"
        id="plugin-tabpanel"
        aria-labelledby={`plugin-tab-${tab}`}
        className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4"
      >
        {visible.map((p) => {
          const hasToggle = p.toggleKey !== null;
          const on = hasToggle ? (values[p.toggleKey as string] ?? false) : true;
          const busy = hasToggle && saving === p.toggleKey;
          const configureHref =
            p.configure === null
              ? null
              : `/dashboard/${guildId}${p.configure ? `/${p.configure}` : ""}`;
          return (
            <article
              key={p.id}
              className="flex flex-col rounded-2xl border border-edge bg-panel p-5"
            >
              <div className="flex items-start justify-between gap-3">
                <span
                  aria-hidden="true"
                  className={`flex h-12 w-12 items-center justify-center rounded-xl text-2xl ring-1 ring-inset transition-colors duration-200 ${
                    on ? "bg-brand/10 ring-brand/25" : "bg-edge ring-edge"
                  }`}
                >
                  {p.emoji}
                </span>
                <span
                  className={`rounded-full px-2.5 py-1 text-xs font-semibold ${
                    on ? "bg-brand/15 text-brand" : "bg-edge text-muted"
                  }`}
                >
                  {on ? (hasToggle ? labels.statusActive : labels.alwaysOn) : labels.statusInactive}
                </span>
              </div>
              <h3 className="mt-4 text-base font-semibold text-fg">{p.name}</h3>
              <p className="mt-1 flex-1 text-sm text-muted">{p.desc}</p>
              <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-edge pt-4">
                {configureHref && (
                  <Link
                    href={configureHref}
                    className="inline-flex min-h-[44px] items-center rounded-lg border border-edge px-4 text-sm font-medium text-fg transition-colors hover:border-brand hover:text-brand focus-visible:outline-2 focus-visible:outline-brand"
                  >
                    {labels.configure}
                    <span aria-hidden="true" className="ml-1.5">
                      →
                    </span>
                  </Link>
                )}
                {hasToggle && (
                  <>
                    {busy && <span className="text-xs text-muted">{labels.saving}</span>}
                    <button
                      type="button"
                      aria-label={fmt(labels[on ? "toggleOff" : "toggleOn"], { title: p.name })}
                      onClick={() => toggle(p.toggleKey as string, !on)}
                      disabled={busy}
                      className={`inline-flex min-h-[44px] items-center rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50 ${
                        on
                          ? "border border-edge text-muted hover:border-red-400 hover:text-red-400"
                          : "bg-brand text-ink hover:bg-brand-deep"
                      }`}
                    >
                      {on ? labels.disable : labels.enable}
                    </button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
