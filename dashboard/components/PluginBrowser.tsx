"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import type { PluginGroup } from "@/lib/plugins";
import { fmt } from "@/lib/i18n/client";

/**
 * Daftar kartu plugin ala MEE6: tab kategori client-side + grid kartu dengan
 * tombol Aktifkan/Nonaktifkan (optimistic) dan tautan Konfigurasi bila ada.
 */
export interface PluginCardData {
  id: string;
  emoji: string;
  group: PluginGroup;
  /** Key settings untuk toggle; null = tool tanpa toggle. */
  toggleKey: string | null;
  /** Path relatif ke /dashboard/[guildId]; "" = overview; null = tanpa tombol. */
  configure: string | null;
  name: string;
  desc: string;
}

interface Labels {
  tabAll: string;
  configure: string;
  enable: string;
  disable: string;
  saving: string;
  toggleError: string;
  toggleOn: string;
  toggleOff: string;
  statusActive: string;
  statusInactive: string;
}

interface Props {
  guildId: string;
  plugins: PluginCardData[];
  initial: Record<string, boolean>;
  groupTitles: Record<PluginGroup, string>;
  heading: string;
  labels: Labels;
}

type TabKey = "all" | PluginGroup;
const TABS: TabKey[] = ["all", "essentials", "engagement", "moderation", "utilities"];
const GROUPS: PluginGroup[] = ["essentials", "engagement", "moderation", "utilities"];

export default function PluginBrowser({ guildId, plugins, initial, groupTitles, heading, labels }: Props) {
  const [active, setActive] = useState<TabKey>("all");
  const [values, setValues] = useState<Record<string, boolean>>(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  function tabLabel(t: TabKey): string {
    return t === "all" ? labels.tabAll : groupTitles[t];
  }

  function onKeyDown(e: React.KeyboardEvent, i: number) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const next = e.key === "ArrowRight" ? (i + 1) % TABS.length : (i - 1 + TABS.length) % TABS.length;
    setActive(TABS[next]);
    tabRefs.current[next]?.focus();
  }

  async function toggle(key: string, v: boolean) {
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
    } catch {
      setValues((prev) => ({ ...prev, [key]: !v }));
      setError(true);
    } finally {
      setSaving(null);
    }
  }

  const visibleGroups: PluginGroup[] = active === "all" ? GROUPS : [active];

  function countFor(t: TabKey): number {
    return t === "all" ? plugins.length : plugins.filter((p) => p.group === t).length;
  }

  function renderCard(p: PluginCardData) {
    const on = p.toggleKey ? (values[p.toggleKey] ?? false) : true;
    const busy = p.toggleKey !== null && saving === p.toggleKey;
    const configureHref =
      p.configure === null ? null : `/dashboard/${guildId}${p.configure ? `/${p.configure}` : ""}`;
    return (
      <article
        key={p.id}
        className="flex min-h-full flex-col rounded-2xl border border-edge bg-panel p-4 transition duration-200 hover:-translate-y-0.5 hover:border-brand/40 hover:shadow-lg hover:shadow-brand/5 focus-within:border-brand/40 sm:p-5"
      >
        <div className="flex items-start gap-3.5">
          <span
            aria-hidden="true"
            className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl text-2xl ring-1 ring-inset transition-colors duration-200 ${
              on ? "bg-brand/10 ring-brand/25" : "bg-edge ring-edge"
            }`}
          >
            {p.emoji}
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <h3 className="truncate text-[15px] font-semibold text-fg" title={p.name}>
              {p.name}
            </h3>
            <p className="mt-1 line-clamp-2 min-h-[2.5rem] text-sm text-muted" title={p.desc}>
              {p.desc}
            </p>
          </div>
          {p.toggleKey && (
            <span
              aria-hidden="true"
              className={`mt-0.5 shrink-0 rounded-full border px-2.5 py-1 text-xs font-semibold ${
                on
                  ? "border-green-500/30 bg-green-500/10 text-green-400"
                  : "border-edge bg-ink text-muted"
              }`}
            >
              {on ? labels.statusActive : labels.statusInactive}
            </span>
          )}
        </div>
        {/* Aksi bawah: mt-auto menjaga sejajar antar kartu dalam satu baris grid */}
        <div className="mt-auto pt-4">
          <div className="flex items-center justify-between gap-3 border-t border-edge pt-3.5">
            {configureHref ? (
              <Link
                href={configureHref}
                className="inline-flex min-h-[44px] items-center gap-1 text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
              >
                {labels.configure}
                <span aria-hidden="true">→</span>
              </Link>
            ) : (
              <span />
            )}
            {p.toggleKey && (
              <div className="flex shrink-0 items-center gap-2">
                {busy && <span className="text-xs text-muted">{labels.saving}</span>}
                <button
                  type="button"
                  aria-pressed={on}
                  aria-label={fmt(labels[on ? "toggleOff" : "toggleOn"], { title: p.name })}
                  disabled={busy}
                  onClick={() => toggle(p.toggleKey as string, !on)}
                  className={
                    on
                      ? "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-4 text-sm font-medium text-muted transition-colors hover:border-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
                      : "inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-ink transition-colors hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
                  }
                >
                  {on ? labels.disable : `+ ${labels.enable}`}
                </button>
              </div>
            )}
          </div>
        </div>
      </article>
    );
  }

  return (
    <div>
      <h1 className="text-xl font-bold tracking-tight text-fg sm:text-2xl">{heading}</h1>
      {error && (
        <p role="alert" className="mb-4 mt-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {labels.toggleError}
        </p>
      )}

      <div
        role="tablist"
        aria-label={labels.tabAll}
        className="mt-5 flex gap-1 overflow-x-auto border-b border-edge"
      >
        {TABS.map((t, i) => (
          <button
            key={t}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            role="tab"
            id={`plugins-tab-${t}`}
            aria-selected={active === t}
            aria-controls={`plugins-panel-${t}`}
            tabIndex={active === t ? 0 : -1}
            onClick={() => setActive(t)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={`flex min-h-[44px] flex-none items-center rounded-t-lg border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand ${
              active === t
                ? "border-brand bg-panel text-fg"
                : "border-transparent text-muted hover:text-fg"
            }`}
          >
            {tabLabel(t)}
            <span
              aria-hidden="true"
              className={`ml-2 rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${
                active === t ? "bg-brand/15 text-brand" : "bg-edge text-muted"
              }`}
            >
              {countFor(t)}
            </span>
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`plugins-panel-${active}`}
        aria-labelledby={`plugins-tab-${active}`}
        className="pt-6"
      >
        {visibleGroups.map((g) => (
          <section key={g} aria-label={groupTitles[g]} className="mb-10 last:mb-0">
            <h2 className="mb-4 flex items-center gap-3 text-base font-semibold tracking-tight text-fg">
              {groupTitles[g]}
              <span aria-hidden="true" className="h-px flex-1 bg-edge" />
            </h2>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 sm:gap-5 xl:grid-cols-3 2xl:grid-cols-4">
              {plugins.filter((p) => p.group === g).map(renderCard)}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
