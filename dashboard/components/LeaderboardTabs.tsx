"use client";

import { useState } from "react";
import { useI18n } from "./I18nProvider";
import { fmt } from "@/lib/i18n/client";

interface LevelRow {
  user_id: string;
  name: string;
  level: number;
  xp: number;
}

interface CoinRow {
  user_id: string;
  name: string;
  coins: number;
}

function rankLabel(i: number): string {
  return i === 0 ? "1" : i === 1 ? "2" : i === 2 ? "3" : String(i + 1);
}

export default function LeaderboardTabs({
  levels,
  coins,
  updatedAt,
}: {
  levels: LevelRow[];
  coins: CoinRow[];
  updatedAt: string;
}) {
  const { lang, dict } = useI18n();
  const t = dict.guild.leaderboard;
  const [tab, setTab] = useState<"levels" | "coins">("levels");
  const locale = lang === "en" ? "en-US" : "id-ID";
  const updated = new Date(updatedAt).toLocaleString(locale, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });

  return (
    <div>
      <div className="flex gap-1 border-b border-edge" role="tablist" aria-label={t.tablistLabel}>
        {(["levels", "coins"] as const).map((tt) => (
          <button
            key={tt}
            role="tab"
            aria-selected={tab === tt}
            onClick={() => setTab(tt)}
            className={`rounded-t-lg px-4 py-2.5 text-sm font-medium focus-visible:outline-2 focus-visible:outline-brand min-h-[44px] ${
              tab === tt ? "bg-panel text-fg border-b-2 border-brand" : "text-muted hover:text-fg"
            }`}
          >
            {tt === "levels" ? t.tabLevels : t.tabCoins}
          </button>
        ))}
      </div>

      <div className="mt-4 overflow-hidden rounded-xl border border-edge bg-panel">
        {tab === "levels" ? (
          levels.length === 0 ? (
            <p className="p-6 text-sm text-muted">{t.emptyLevels}</p>
          ) : (
            <ol className="divide-y divide-edge">
              {levels.map((r, i) => (
                <li key={r.user_id} className="flex flex-col gap-1 px-4 py-3 sm:px-5 md:flex-row md:items-center md:gap-4">
                  <div className="flex min-w-0 items-center gap-3 md:flex-1">
                    <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-edge font-mono text-xs text-muted">
                      {rankLabel(i)}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-sm text-fg">{r.name}</span>
                  </div>
                  <div className="flex shrink-0 items-center gap-3 pl-10 font-mono text-xs text-muted md:pl-0 md:text-sm">
                    <span>Lv {r.level}</span>
                    <span>{r.xp.toLocaleString(locale)} XP</span>
                  </div>
                </li>
              ))}
            </ol>
          )
        ) : coins.length === 0 ? (
          <p className="p-6 text-sm text-muted">{t.emptyCoins}</p>
        ) : (
          <ol className="divide-y divide-edge">
            {coins.map((r, i) => (
              <li key={r.user_id} className="flex flex-col gap-1 px-4 py-3 sm:px-5 md:flex-row md:items-center md:gap-4">
                <div className="flex min-w-0 items-center gap-3 md:flex-1">
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-edge font-mono text-xs text-muted">
                    {rankLabel(i)}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-sm text-fg">{r.name}</span>
                </div>
                <div className="shrink-0 pl-10 font-mono text-xs text-brand md:pl-0 md:text-sm">
                  🪙 {r.coins.toLocaleString(locale)}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
      <p className="mt-3 text-xs text-muted">{fmt(t.updatedAt, { time: updated })}</p>
    </div>
  );
}
