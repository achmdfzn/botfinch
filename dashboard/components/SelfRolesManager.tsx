"use client";

import { useState } from "react";
import type { SnapshotRole } from "@/lib/db";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface Row {
  id: number;
  message_id: string;
  emoji: string;
  role_id: string;
}

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

export default function SelfRolesManager({
  guildId,
  roles,
  initialRows,
}: {
  guildId: string;
  roles: SnapshotRole[];
  initialRows: Row[];
}) {
  const { dict } = useI18n();
  const g = dict.guild.selfroles;

  const [rows, setRows] = useState<Row[]>(initialRows);
  const [loading, setLoading] = useState(false);
  const [messageId, setMessageId] = useState("");
  const [emoji, setEmoji] = useState("");
  const [roleId, setRoleId] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  async function reload() {
    setLoading(true);
    try {
      const res = await fetch(`/api/guilds/${guildId}/selfroles`);
      const data = await res.json();
      setRows(data.selfroles ?? []);
    } catch {
      /* biarkan kosong */
    } finally {
      setLoading(false);
    }
  }

  const roleName = (id: string) => roles.find((r) => r.id === id)?.name ?? id;

  async function add() {
    setStatus("idle");
    const res = await fetch(`/api/guilds/${guildId}/selfroles`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id: messageId.trim(), emoji: emoji.trim(), role_id: roleId }),
    });
    if (res.ok) {
      setMessageId("");
      setEmoji("");
      setRoleId("");
      setStatus("ok");
      reload();
    } else {
      setStatus("error");
    }
  }

  async function remove(message_id: string, em: string) {
    const res = await fetch(`/api/guilds/${guildId}/selfroles`, {
      method: "DELETE",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message_id, emoji: em }),
    });
    if (res.ok) reload();
  }

  return (
    <div>
      <div className="rounded-xl border border-edge bg-panel p-5">
        <h2 className="text-sm font-semibold text-fg">{g.formTitle}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="sr-msg" className="text-xs font-medium text-muted">{g.msgIdLabel}</label>
            <input
              id="sr-msg"
              value={messageId}
              onChange={(e) => setMessageId(e.target.value)}
              placeholder={g.msgIdPlaceholder}
              inputMode="numeric"
              className={`${inputCls} mt-1 w-full`}
            />
            <p className="mt-1 text-xs text-muted">{g.msgIdHint}</p>
          </div>
          <div>
            <label htmlFor="sr-emoji" className="text-xs font-medium text-muted">{g.emojiLabel}</label>
            <input
              id="sr-emoji"
              value={emoji}
              onChange={(e) => setEmoji(e.target.value)}
              placeholder={g.emojiPlaceholder}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
        </div>
        <div className="mt-3">
          <label htmlFor="sr-role" className="text-xs font-medium text-muted">{g.roleLabel}</label>
          <select id="sr-role" value={roleId} onChange={(e) => setRoleId(e.target.value)} className={`${inputCls} mt-1 w-full`}>
            <option value="">{g.selectRole}</option>
            {roles.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          {roles.length === 0 && (
            <p className="mt-1 text-xs text-muted">{g.noRolesHint}</p>
          )}
        </div>
        <button
          onClick={add}
          disabled={!messageId.trim() || !emoji.trim() || !roleId}
          className="mt-4 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {dict.common.add}
        </button>
        {status === "ok" && <p role="status" className="mt-2 text-sm text-brand">{g.addOk}</p>}
        {status === "error" && <p role="alert" className="mt-2 text-sm text-red-400">{g.addError}</p>}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-fg">{fmt(g.listTitle, { n: rows.length })}</h2>
        {loading ? (
          <p className="mt-3 text-sm text-muted">{dict.common.loading}</p>
        ) : rows.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{g.emptyList}</p>
        ) : (
          <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
            {rows.map((r) => (
              <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                <span className="text-xl" aria-hidden="true">{r.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-fg">{roleName(r.role_id)}</p>
                  <p className="font-mono text-xs text-muted">{fmt(g.rowMessage, { id: r.message_id })}</p>
                </div>
                <button
                  onClick={() => remove(r.message_id, r.emoji)}
                  className="shrink-0 rounded-lg border border-edge px-3 py-2 text-sm text-muted hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
                >
                  {dict.common.remove}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
