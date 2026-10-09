"use client";

import { useState } from "react";
import type { SnapshotChannel } from "@/lib/db";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface Active {
  id: number;
  channel_id: string;
  prize: string;
  winners: number;
  ends_at: string;
  participants: number;
}

interface ReqRow {
  id: number;
  prize: string;
  winners: number;
  duration_minutes: number;
  status: string;
  note: string;
  created_at: string;
}

const inputCls =
  "rounded-lg border border-edge bg-ink px-3 py-2 text-sm text-fg focus-visible:outline-2 focus-visible:outline-brand min-h-[44px]";

function formatEnds(iso: string, locale: string): string {
  if (!iso) return "-";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? "-" : d.toLocaleString(locale, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function GiveawayManager({
  guildId,
  channels,
  initialActive,
  initialRequests,
}: {
  guildId: string;
  channels: SnapshotChannel[];
  initialActive: Active[];
  initialRequests: ReqRow[];
}) {
  const { lang, dict } = useI18n();
  const g = dict.guild.giveaway;
  const locale = lang === "en" ? "en-US" : "id-ID";

  const [active, setActive] = useState<Active[]>(initialActive);
  const [requests, setRequests] = useState<ReqRow[]>(initialRequests);
  const [loading, setLoading] = useState(false);
  const [channelId, setChannelId] = useState("");
  const [prize, setPrize] = useState("");
  const [winners, setWinners] = useState(1);
  const [duration, setDuration] = useState(60);
  const [status, setStatus] = useState<"idle" | "ok" | "error">("idle");

  const textChannels = channels.filter((c) => c.type === 0 || c.type === 5);

  async function reload() {
    setLoading(true);
    try {
      const res = await fetch(`/api/guilds/${guildId}/giveaways`);
      const data = await res.json();
      setActive(data.active ?? []);
      setRequests(data.requests ?? []);
    } catch {
      /* biarkan kosong */
    } finally {
      setLoading(false);
    }
  }

  async function create() {
    setStatus("idle");
    const res = await fetch(`/api/guilds/${guildId}/giveaways`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel_id: channelId, prize: prize.trim(), winners, duration_minutes: duration }),
    });
    if (res.ok) {
      setPrize("");
      setStatus("ok");
      reload();
    } else {
      setStatus("error");
    }
  }

  return (
    <div>
      <div className="rounded-xl border border-edge bg-panel p-5">
        <h2 className="text-sm font-semibold text-fg">{g.formTitle}</h2>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <div>
            <label htmlFor="gw-channel" className="text-xs font-medium text-muted">{g.channelLabel}</label>
            <select id="gw-channel" value={channelId} onChange={(e) => setChannelId(e.target.value)} className={`${inputCls} mt-1 w-full`}>
              <option value="">{g.selectChannel}</option>
              {textChannels.map((c) => (
                <option key={c.id} value={c.id}>
                  # {c.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label htmlFor="gw-prize" className="text-xs font-medium text-muted">{g.prizeLabel}</label>
            <input
              id="gw-prize"
              value={prize}
              onChange={(e) => setPrize(e.target.value)}
              placeholder={g.prizePlaceholder}
              maxLength={100}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
          <div>
            <label htmlFor="gw-winners" className="text-xs font-medium text-muted">{g.winnersLabel}</label>
            <input
              id="gw-winners"
              type="number"
              min={1}
              max={25}
              value={winners}
              onChange={(e) => setWinners(Number(e.target.value))}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
          <div>
            <label htmlFor="gw-duration" className="text-xs font-medium text-muted">{g.durationLabel}</label>
            <input
              id="gw-duration"
              type="number"
              min={1}
              max={10080}
              value={duration}
              onChange={(e) => setDuration(Number(e.target.value))}
              className={`${inputCls} mt-1 w-full`}
            />
          </div>
        </div>
        <button
          onClick={create}
          disabled={!channelId || !prize.trim()}
          className="mt-4 rounded-lg bg-brand px-6 py-2.5 text-sm font-semibold text-ink hover:bg-brand-deep disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand min-h-[44px]"
        >
          {g.create}
        </button>
        {status === "ok" && <p role="status" className="mt-2 text-sm text-brand">{g.createOk}</p>}
        {status === "error" && <p role="alert" className="mt-2 text-sm text-red-400">{g.createError}</p>}
      </div>

      <div className="mt-6">
        <h2 className="text-sm font-semibold text-fg">{g.activeTitle}</h2>
        {loading ? (
          <p className="mt-3 text-sm text-muted">{dict.common.loading}</p>
        ) : active.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{g.emptyActive}</p>
        ) : (
          <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
            {active.map((gv) => (
              <li key={gv.id} className="px-5 py-3">
                <p className="text-sm font-medium text-fg">{gv.prize}</p>
                <p className="mt-1 font-mono text-xs text-muted">
                  {fmt(g.activeLine, {
                    participants: gv.participants,
                    winners: gv.winners,
                    endsAt: formatEnds(gv.ends_at, locale),
                  })}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>

      {requests.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-semibold text-fg">{g.historyTitle}</h2>
          <ul className="mt-3 divide-y divide-edge overflow-hidden rounded-xl border border-edge bg-panel">
            {requests.map((r) => {
              const reqStatus =
                r.status === "pending" ? g.statusPending
                : r.status === "done" ? g.statusDone
                : fmt(g.statusFailed, { note: r.note || "-" });
              return (
                <li key={r.id} className="px-5 py-3">
                  <p className="text-sm font-medium text-fg">{r.prize}</p>
                  <p className="mt-1 font-mono text-xs text-muted">
                    {fmt(g.requestLine, { status: reqStatus, duration: r.duration_minutes, winners: r.winners })}
                  </p>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
