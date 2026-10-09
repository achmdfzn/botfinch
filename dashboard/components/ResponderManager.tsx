"use client";

import { useState } from "react";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface Row {
  id: number;
  trigger: string;
  response: string;
}

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

export default function ResponderManager({
  guildId,
  initialRows,
}: {
  guildId: string;
  initialRows: Row[];
}) {
  const { dict } = useI18n();
  const g = dict.guild.responder;

  const [rows, setRows] = useState<Row[]>(initialRows);
  const [trigger, setTrigger] = useState("");
  const [response, setResponse] = useState("");
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");
  // Guard klik ganda: satu request tambah dalam satu waktu.
  const [saving, setSaving] = useState(false);
  // Error khusus refresh pasca-mutasi: list lama tetap tampil + peringatan.
  const [refreshError, setRefreshError] = useState(false);
  // Guard klik ganda per baris saat hapus.
  const [busyRows, setBusyRows] = useState<ReadonlySet<number>>(new Set());

  async function reload() {
    setRefreshError(false);
    try {
      const res = await fetch(`/api/guilds/${guildId}/autoresponses`);
      if (!res.ok) throw new Error("http");
      const data = await res.json();
      setRows(data.autoresponses ?? []);
    } catch {
      setRefreshError(true);
    }
  }

  async function add() {
    if (saving) return;
    setSaving(true);
    setStatus("idle");
    try {
      // Trim payload: tombol sudah disabled bila kosong-setelah-trim,
      // tanpa ini trigger/response tersimpan beserta spasi pinggirnya.
      const res = await fetch(`/api/guilds/${guildId}/autoresponses`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trigger: trigger.trim(), response: response.trim() }),
      });
      if (res.ok) {
        setTrigger("");
        setResponse("");
        setStatus("ok");
        reload();
      } else {
        setStatus("error");
      }
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  }

  async function remove(id: number, preview: string) {
    if (!confirm(fmt(g.confirmDelete, { preview }))) return;
    if (busyRows.has(id)) return;
    setBusyRows((prev) => new Set(prev).add(id));
    try {
      const res = await fetch(`/api/guilds/${guildId}/autoresponses?id=${id}`, { method: "DELETE" });
      if (res.ok) reload();
    } finally {
      setBusyRows((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
    }
  }

  return (
    <div>
      <div className="rounded-xl border border-edge bg-panel p-5">
        <h2 className="text-sm font-semibold text-fg">{g.formTitle}</h2>
        <div className="mt-3 grid gap-3">
          <div>
            <label htmlFor="ar-trigger" className="text-xs font-medium text-muted">{g.triggerLabel}</label>
            <input
              id="ar-trigger"
              value={trigger}
              onChange={(e) => setTrigger(e.target.value)}
              placeholder={g.triggerPlaceholder}
              maxLength={100}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
          <div>
            <label htmlFor="ar-response" className="text-xs font-medium text-muted">{g.responseLabel}</label>
            <textarea
              id="ar-response"
              value={response}
              onChange={(e) => setResponse(e.target.value)}
              placeholder={g.responsePlaceholder}
              rows={2}
              maxLength={500}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
        </div>
        <button
          onClick={add}
          disabled={!trigger.trim() || !response.trim() || saving}
          className="mt-4 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
        >
          {saving ? dict.settings.saving : dict.common.add}
        </button>
        {status === "ok" && <p role="status" className="mt-2 text-sm text-brand">{g.addOk}</p>}
        {status === "error" && <p role="alert" className="mt-2 text-sm text-red-400">{g.addError}</p>}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-fg">{fmt(g.listTitle, { n: rows.length })}</h2>
        {rows.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{g.emptyList}</p>
        ) : (
          <>
            {refreshError && (
              <p role="alert" className="mt-3 text-sm text-red-400">{dict.common.refreshError}</p>
            )}
            <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
              {rows.map((r) => (
                <li key={r.id} className="flex items-center gap-3 px-5 py-3">
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-fg">{r.trigger}</p>
                    <p className="truncate text-sm text-muted">→ {r.response}</p>
                  </div>
                  <button
                    onClick={() => remove(r.id, r.trigger)}
                    disabled={busyRows.has(r.id)}
                    className="shrink-0 rounded-lg border border-edge px-3 py-2 text-sm text-muted hover:bg-edge disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]"
                  >
                    {dict.common.remove}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
