"use client";

import { useState } from "react";
import Toggle from "./Toggle";
import { useI18n } from "./I18nProvider";
import { fmt } from "@/lib/i18n/client";
import type { Dict } from "@/lib/i18n/client";
import type { FieldDef, ModuleDef } from "@/lib/settings";
import type { SnapshotChannel, SnapshotRole } from "@/lib/db";

interface Props {
  guildId: string;
  guildName: string;
  modules: ModuleDef[];
  initial: Record<string, boolean | string | number>;
  channels: SnapshotChannel[];
  roles: SnapshotRole[];
}

interface LevelRole {
  level: number;
  role_id: string;
}

interface FieldTexts {
  label?: string;
  hint?: string;
  placeholder?: string;
}

type ModuleDict = Dict["settings"]["modules"][keyof Dict["settings"]["modules"]];

function moduleDict(dictModules: Record<string, ModuleDict>, key: string): ModuleDict | undefined {
  return dictModules[key.replace(/_enabled$/, "")];
}

function parseLevelRoles(s: string): LevelRole[] {
  try {
    const arr = JSON.parse(s);
    return Array.isArray(arr) ? arr.filter((r) => r && Number.isInteger(r.level) && typeof r.role_id === "string") : [];
  } catch {
    return [];
  }
}

function FieldInput({
  field,
  texts,
  value,
  onChange,
  channels,
  roles,
}: {
  field: FieldDef;
  texts?: FieldTexts;
  value: boolean | string | number;
  onChange: (v: boolean | string | number) => void;
  channels: SnapshotChannel[];
  roles: SnapshotRole[];
}) {
  const { dict } = useI18n();
  const s = dict.settings;
  const label = texts?.label ?? field.label;
  const placeholder = texts?.placeholder ?? field.placeholder;
  const inputCls =
    "mt-1 w-full rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

  if (field.kind === "toggle") {
    return <Toggle checked={Boolean(value)} onChange={onChange} label={label} />;
  }

  if (field.kind === "number") {
    return (
      <input
        id={`f-${field.key}`}
        type="number"
        min={field.min}
        max={field.max}
        value={Number(value ?? 0)}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`${inputCls} w-full sm:w-32`}
      />
    );
  }

  if (field.kind === "textarea") {
    return (
      <textarea
        id={`f-${field.key}`}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={2}
        maxLength={500}
        className={inputCls}
      />
    );
  }

  if (field.kind === "channel") {
    const textChannels = channels.filter((c) => c.type === 0 || c.type === 5);
    return (
      <select
        id={`f-${field.key}`}
        value={String(value ?? "")}
        onChange={(e) => onChange(e.target.value)}
        className={inputCls}
      >
        <option value="">{s.channelAuto}</option>
        {textChannels.map((c) => (
          <option key={c.id} value={c.id}>
            # {c.name}
          </option>
        ))}
      </select>
    );
  }

  if (field.kind === "levelroles") {
    const rows = parseLevelRoles(String(value ?? "[]"));
    const setRows = (next: LevelRole[]) => onChange(JSON.stringify(next));
    return (
      <div className="mt-1 space-y-2">
        {rows.map((r, i) => (
          <div key={i} className="flex items-center gap-2">
            <input
              type="number"
              min={1}
              max={500}
              value={r.level}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...r, level: Math.max(1, Math.min(500, Number(e.target.value) || 1)) };
                setRows(next);
              }}
              aria-label={s.levelAria}
              className="w-20 rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
            />
            <select
              value={r.role_id}
              onChange={(e) => {
                const next = [...rows];
                next[i] = { ...r, role_id: e.target.value };
                setRows(next);
              }}
              aria-label={s.roleAria}
              className="min-w-0 flex-1 rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
            >
              <option value="">{s.selectRole}</option>
              {roles.map((ro) => (
                <option key={ro.id} value={ro.id}>
                  {ro.name}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => setRows(rows.filter((_, j) => j !== i))}
              aria-label={s.removeRowAria}
              className="shrink-0 rounded-lg border border-edge px-3 py-2 text-sm text-muted hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
            >
              {dict.common.remove}
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={() => setRows([...rows, { level: 5, role_id: "" }].slice(0, 40))}
          className="rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
        >
          {s.addLevelRole}
        </button>
      </div>
    );
  }

  return (
    <input
      id={`f-${field.key}`}
      type="text"
      value={String(value ?? "")}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={inputCls}
    />
  );
}

export default function SettingsForm({ guildId, guildName, modules, initial, channels, roles }: Props) {
  const { dict } = useI18n();
  const s = dict.settings;
  const [values, setValues] = useState(initial);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  async function save() {
    setSaving(true);
    setStatus("idle");
    try {
      const res = await fetch(`/api/guilds/${guildId}/settings`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(values),
      });
      setStatus(res.ok ? "ok" : "error");
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <div className="grid gap-3">
        {modules.map((m) => {
          const t = moduleDict(dict.settings.modules as Record<string, ModuleDict>, m.key);
          const title = t?.title ?? m.title;
          const desc = t?.desc ?? m.description;
          const fieldsTexts = (t?.fields as Record<string, FieldTexts> | undefined) ?? {};
          return (
            <div key={m.key} className="rounded-xl border border-edge bg-panel p-4 sm:p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0">
                  <h2 className="text-sm font-semibold text-fg">{title}</h2>
                  <p className="mt-1 text-sm text-muted">{desc}</p>
                </div>
                <Toggle
                  checked={Boolean(values[m.key])}
                  onChange={(v) => setValues((sv) => ({ ...sv, [m.key]: v }))}
                  label={fmt(dict.guild.modul[values[m.key] ? "toggleOn" : "toggleOff"], { title })}
                />
              </div>
              {Boolean(values[m.key]) && m.fields.length > 0 && (
                <div className="mt-4 space-y-4 border-t border-edge pt-4">
                  {m.fields.map((f) => {
                    const texts = fieldsTexts[f.key];
                    const label = texts?.label ?? f.label;
                    const hint = texts?.hint ?? f.hint;
                    return f.kind === "toggle" ? (
                      <div key={f.key} className="flex items-center justify-between gap-4">
                        <span className="text-sm text-fg">{label}</span>
                        <FieldInput
                          field={f}
                          texts={texts}
                          value={values[f.key] ?? false}
                          onChange={(v) => setValues((sv) => ({ ...sv, [f.key]: v }))}
                          channels={channels}
                          roles={roles}
                        />
                      </div>
                    ) : (
                      <div key={f.key}>
                        <label htmlFor={`f-${f.key}`} className="text-xs font-medium text-muted">
                          {label}
                        </label>
                        <FieldInput
                          field={f}
                          texts={texts}
                          value={values[f.key] ?? ""}
                          onChange={(v) => setValues((sv) => ({ ...sv, [f.key]: v }))}
                          channels={channels}
                          roles={roles}
                        />
                        {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="mt-6 flex flex-wrap items-center gap-4">
        <button
          onClick={save}
          disabled={saving}
          className="rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {saving ? s.saving : s.save}
        </button>
        {status === "ok" && (
          <p role="status" className="text-sm text-brand">
            {s.saveOk}
          </p>
        )}
        {status === "error" && (
          <p role="alert" className="text-sm text-red-400">
            {s.saveError}
          </p>
        )}
      </div>
      <p className="mt-4 text-xs text-muted">
        {fmt(s.footnote, { name: guildName })}
      </p>
    </div>
  );
}
