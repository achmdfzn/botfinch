"use client";

import { useState } from "react";
import Link from "next/link";
import type { PluginGroup } from "@/lib/plugins";
import { fmt } from "@/lib/i18n/client";
import Toggle from "./Toggle";

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
  configure: string;
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

const GROUP_ORDER: PluginGroup[] = ["essentials", "engagement", "moderation", "utilities"];

export default function PluginsManager({ guildId, plugins, initial, groupTitles, labels }: Props) {
  const [values, setValues] = useState<Record<string, boolean>>(initial);
  const [saving, setSaving] = useState<string | null>(null);
  const [error, setError] = useState<boolean>(false);

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

  return (
    <div className="space-y-8">
      {error && (
        <p role="alert" className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {labels.toggleError}
        </p>
      )}
      {GROUP_ORDER.map((group) => {
        const items = plugins.filter((p) => p.group === group);
        if (items.length === 0) return null;
        return (
          <section key={group} aria-label={groupTitles[group]}>
            <h2 className="text-sm font-semibold text-fg">{groupTitles[group]}</h2>
            <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2">
              {items.map((p) => {
                const on = p.toggleKey ? (values[p.toggleKey] ?? false) : true;
                const configureHref =
                  p.configure === null ? null : `/dashboard/${guildId}${p.configure ? `/${p.configure}` : ""}`;
                return (
                  <article
                    key={p.id}
                    className="flex flex-col gap-3 rounded-xl border border-edge bg-panel p-4 sm:p-5"
                  >
                    <div className="flex items-start gap-3">
                      <span aria-hidden="true" className="text-2xl leading-none">
                        {p.emoji}
                      </span>
                      <div className="min-w-0 flex-1">
                        <h3 className="text-base font-semibold text-fg">{p.name}</h3>
                        <p className="mt-0.5 truncate text-sm text-muted" title={p.desc}>
                          {p.desc}
                        </p>
                      </div>
                      {p.toggleKey && (
                        <div className="flex shrink-0 items-center gap-2">
                          {saving === p.toggleKey && (
                            <span className="text-xs text-muted">{labels.saving}</span>
                          )}
                          <Toggle
                            checked={on}
                            onChange={(v) => toggle(p.toggleKey as string, v)}
                            label={fmt(labels[on ? "toggleOn" : "toggleOff"], { title: p.name })}
                          />
                        </div>
                      )}
                    </div>
                    {configureHref && (
                      <div>
                        <Link
                          href={configureHref}
                          className="inline-flex min-h-[44px] items-center text-sm font-medium text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                        >
                          {labels.configure} →
                        </Link>
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}
