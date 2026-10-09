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
}

interface Props {
  guildId: string;
  plugins: PluginCardData[];
  initial: Record<string, boolean>;
  groupTitles: Record<PluginGroup, string>;
  labels: Labels;
}

type TabKey = "all" | PluginGroup;
const TABS: TabKey[] = ["all", "essentials", "engagement", "moderation", "utilities"];

export default function PluginBrowser({ guildId, plugins, initial, groupTitles, labels }: Props) {
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

  const visible = active === "all" ? plugins : plugins.filter((p) => p.group === active);

  return (
    <div>
      {error && (
        <p role="alert" className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {labels.toggleError}
        </p>
      )}

      <div
        role="tablist"
        aria-label={labels.tabAll}
        className="flex gap-1 overflow-x-auto border-b border-edge"
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
            className={`min-h-[44px] flex-none rounded-t-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand ${
              active === t ? "border-b-2 border-brand bg-panel text-fg" : "text-muted hover:text-fg"
            }`}
          >
            {tabLabel(t)}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id={`plugins-panel-${active}`}
        aria-labelledby={`plugins-tab-${active}`}
        className="pt-6"
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {visible.map((p) => {
            const on = p.toggleKey ? (values[p.toggleKey] ?? false) : true;
            const configureHref =
              p.configure === null ? null : `/dashboard/${guildId}${p.configure ? `/${p.configure}` : ""}`;
            return (
              <article
                key={p.id}
                className="flex flex-col justify-between gap-4 rounded-xl border border-edge bg-panel p-4 sm:p-5"
              >
                <div className="flex items-start gap-3">
                  <span
                    aria-hidden="true"
                    className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-brand/10 text-2xl"
                  >
                    {p.emoji}
                  </span>
                  <div className="min-w-0">
                    <h3 className="font-semibold text-fg">{p.name}</h3>
                    <p className="mt-1 line-clamp-2 text-sm text-muted" title={p.desc}>
                      {p.desc}
                    </p>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-3">
                  {configureHref ? (
                    <Link
                      href={configureHref}
                      className="inline-flex min-h-[44px] items-center text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                    >
                      {labels.configure} →
                    </Link>
                  ) : (
                    <span />
                  )}
                  {p.toggleKey && (
                    <div className="flex shrink-0 items-center gap-2">
                      {saving === p.toggleKey && (
                        <span className="text-xs text-muted">{labels.saving}</span>
                      )}
                      <button
                        type="button"
                        aria-pressed={on}
                        aria-label={fmt(labels[on ? "toggleOff" : "toggleOn"], { title: p.name })}
                        disabled={saving === p.toggleKey}
                        onClick={() => toggle(p.toggleKey as string, !on)}
                        className={
                          on
                            ? "inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-4 text-sm font-medium text-muted hover:border-muted hover:text-fg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
                            : "inline-flex min-h-[44px] items-center justify-center rounded-lg bg-brand px-4 text-sm font-semibold text-ink hover:bg-brand-deep focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-50"
                        }
                      >
                        {on ? labels.disable : `+ ${labels.enable}`}
                      </button>
                    </div>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      </div>
    </div>
  );
}
