"use client";

import { useState } from "react";
import Link from "next/link";
import type { ModuleDef } from "@/lib/settings";
import { useI18n } from "./I18nProvider";
import { fmt } from "@/lib/i18n/client";
import Toggle from "./Toggle";

export default function ModuleToggles({
  guildId,
  modules,
  initial,
}: {
  guildId: string;
  modules: ModuleDef[];
  initial: Record<string, boolean>;
}) {
  const { dict } = useI18n();
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
    <div>
      {error && (
        <p role="alert" className="mb-4 rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-400">
          {dict.guild.modul.toggleError}
        </p>
      )}
      <ul className="grid gap-3">
        {modules.map((m) => {
          const on = values[m.key] ?? false;
          const t = (dict.settings.modules as Record<string, { title?: string; desc?: string }>)[m.key.replace(/_enabled$/, "")];
          const title = t?.title ?? m.title;
          const desc = t?.desc ?? m.description;
          return (
            <li
              key={m.key}
              className="flex flex-wrap items-center gap-4 rounded-xl border border-edge bg-panel p-4 sm:p-5"
            >
              <div className="min-w-0 flex-1 basis-56">
                <p className="text-base font-semibold text-fg">{title}</p>
                <p className="mt-1 text-sm text-muted">{desc}</p>
                <Link
                  href={`/dashboard/${guildId}`}
                  className="mt-2 inline-flex min-h-[44px] items-center text-sm text-brand hover:underline focus-visible:outline-2 focus-visible:outline-brand"
                >
                  {dict.guild.modul.detailLink}
                </Link>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                {saving === m.key && <span className="text-xs text-muted">{dict.guild.modul.saving}</span>}
                <Toggle
                  checked={on}
                  onChange={(v) => toggle(m.key, v)}
                  label={fmt(dict.guild.modul[on ? "toggleOn" : "toggleOff"], { title })}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
