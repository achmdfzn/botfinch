"use client";

import { useEffect, useRef, useState } from "react";
import GuildCard from "@/components/GuildCard";
import EmptyState from "@/components/EmptyState";
import { useI18n } from "@/components/I18nProvider";
import { fmt } from "@/lib/i18n/client";

export interface GuildLite {
  id: string;
  name: string;
  icon: string | null;
  memberCount: number | null;
  /** True bila user login adalah owner server ini. */
  isOwner?: boolean;
}

interface Props {
  initialInBot: GuildLite[];
  initialNotInBot: GuildLite[];
  initialHasSnapshot: boolean;
}

interface SyncGuild {
  id: string;
  name: string;
  icon: string | null;
  member_count: number;
}

interface SyncStatus {
  pushed_at: string | null;
  guilds: SyncGuild[];
}

type Filter = "all" | "in" | "out";

const POLL_MS = 15_000;
const MAX_POLLS = 20; // ~5 menit lalu berhenti sendiri

/** Urutan stabil berdasarkan nama (dipakai juga untuk guild yang pindah section). */
const byName = (locale: string) => (a: GuildLite, b: GuildLite) =>
  a.name.localeCompare(b.name, locale, { sensitivity: "base" });

/**
 * Daftar server dengan auto-refresh: tiap POLL_MS menanyakan
 * /api/sync-status; guild yang baru terdeteksi di snapshot bot langsung
 * pindah ke daftar "Terpasang" tanpa reload manual. Berhenti sendiri bila
 * semua guild sudah terdeteksi atau batas waktu tercapai.
 */
export default function GuildListSync({ initialInBot, initialNotInBot, initialHasSnapshot }: Props) {
  const { dict, lang } = useI18n();
  const d = dict.dashboard;
  const locale = lang === "id" ? "id-ID" : "en-US";
  const cmp = byName(locale);
  const [inBot, setInBot] = useState<GuildLite[]>(() => [...initialInBot].sort(cmp));
  const [notInBot, setNotInBot] = useState<GuildLite[]>(() => [...initialNotInBot].sort(cmp));
  const [hasSnapshot, setHasSnapshot] = useState(initialHasSnapshot);
  const [checking, setChecking] = useState(initialNotInBot.length > 0);
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState<Filter>("all");
  // ref agar closure interval selalu baca daftar pending terbaru
  const pendingRef = useRef<GuildLite[]>([...initialNotInBot].sort(cmp));

  useEffect(() => {
    if (pendingRef.current.length === 0) return;
    let polls = 0;
    const timer = setInterval(async () => {
      // Jeda polling saat tab tidak aktif: hemat request & baterai.
      if (document.hidden) return;
      polls += 1;
      let data: SyncStatus | null = null;
      try {
        const res = await fetch("/api/sync-status", { cache: "no-store" });
        if (res.ok) data = (await res.json()) as SyncStatus;
      } catch {
        // gagal sekali -> coba lagi di poll berikut
      }
      if (data) {
        if (data.pushed_at) setHasSnapshot(true);
        const seen = new Map((data.guilds ?? []).map((g) => [String(g.id), g]));
        const moved: GuildLite[] = [];
        pendingRef.current = pendingRef.current.filter((g) => {
          const s = seen.get(g.id);
          if (s) {
            // Snapshot bot tidak membawa info owner: pertahankan isOwner
            // dari data Discord awal.
            moved.push({ id: s.id, name: s.name, icon: s.icon, memberCount: s.member_count, isOwner: g.isOwner });
            return false;
          }
          return true;
        });
        if (moved.length > 0) {
          setNotInBot([...pendingRef.current]);
          // Kartu yang pindah section ikut diurutkan by name (B-009a).
          setInBot((cur) => [...cur, ...moved].sort(cmp));
        }
      }
      if (pendingRef.current.length === 0 || polls >= MAX_POLLS) {
        clearInterval(timer);
        setChecking(false);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const memberText = (n: number | null) =>
    n === null ? null : fmt(d.cardMembers, { n: n.toLocaleString(locale) });

  // --- Search + filter client-side (B-008) ---
  const q = query.trim().toLowerCase();
  const matchName = (g: GuildLite) => q === "" || g.name.toLowerCase().includes(q);
  const visInBot = filter === "out" ? [] : inBot.filter(matchName);
  const visNotInBot = filter === "in" ? [] : notInBot.filter(matchName);
  const shownCount = visInBot.length + visNotInBot.length;
  const searched = q !== "" || filter !== "all";

  const resetSearch = () => {
    setQuery("");
    setFilter("all");
  };

  const filters: { value: Filter; label: string }[] = [
    { value: "all", label: d.filterAll },
    { value: "in", label: d.filterInBot },
    { value: "out", label: d.filterNotInBot },
  ];

  const cardProps = (g: GuildLite, inBotSection: boolean) => ({
    id: g.id,
    name: g.name,
    icon: g.icon,
    memberText: inBotSection ? memberText(g.memberCount) : null,
    inBot: inBotSection,
    openLabel: d.cardOpen,
    inviteLabel: d.cardInvite,
    noDataLabel: d.cardNoData,
    isOwner: g.isOwner,
  });

  return (
    <>
      {/* Bar pencarian + filter, tepat di bawah subtitle halaman */}
      <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <svg
            viewBox="0 0 20 20"
            fill="none"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
            className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted"
          >
            <circle cx="9" cy="9" r="6" />
            <path d="m13.5 13.5 3 3" strokeLinecap="round" />
          </svg>
          <label htmlFor="guild-search" className="sr-only">
            {d.searchLabel}
          </label>
          <input
            id="guild-search"
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={d.searchPlaceholder}
            autoComplete="off"
            className="w-full rounded-lg border border-edge bg-panel py-2.5 pl-9 pr-3 text-sm text-fg placeholder:text-muted focus:border-brand focus:outline-none"
          />
        </div>
        <div
          role="group"
          aria-label={d.filterLabel}
          className="inline-flex shrink-0 gap-1 self-start rounded-lg border border-edge bg-panel p-1 sm:self-auto"
        >
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-pressed={filter === f.value}
              onClick={() => setFilter(f.value)}
              className={`min-h-[44px] rounded-md px-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-brand ${
                filter === f.value ? "bg-brand font-semibold text-ink" : "text-muted hover:text-fg"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>
      {/* Pengumuman jumlah hasil untuk screen reader */}
      <p className="sr-only" aria-live="polite">
        {fmt(d.searchResults, { n: shownCount })}
      </p>

      {visInBot.length > 0 && (
        <section className="mt-8" aria-label={d.sectionInBot}>
          <div className="flex items-center gap-3">
            <h2 className="shrink-0 text-xs font-semibold uppercase tracking-wider text-muted">
              {d.sectionInBot}
            </h2>
            <span className="shrink-0 rounded-full bg-edge px-2 py-0.5 text-[11px] font-medium text-muted">
              {fmt(d.sectionCount, { n: visInBot.length })}
            </span>
            <span className="h-px flex-1 bg-edge" aria-hidden="true" />
          </div>
          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visInBot.map((g) => (
              <GuildCard key={g.id} {...cardProps(g, true)} />
            ))}
          </div>
        </section>
      )}

      {visNotInBot.length > 0 && (
        <section className="mt-10" aria-label={d.sectionNotInBot}>
          <div className="flex items-center gap-3">
            <h2 className="shrink-0 text-xs font-semibold uppercase tracking-wider text-muted">
              {d.sectionNotInBot}
            </h2>
            <span className="shrink-0 rounded-full bg-edge px-2 py-0.5 text-[11px] font-medium text-muted">
              {fmt(d.sectionCount, { n: visNotInBot.length })}
            </span>
            <span className="h-px flex-1 bg-edge" aria-hidden="true" />
          </div>
          <div className="mt-5 grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {visNotInBot.map((g) => (
              <GuildCard key={g.id} {...cardProps(g, false)} />
            ))}
          </div>
          <p className="mt-4 text-xs text-muted" role="status">
            {checking ? fmt(d.checkingInterval, { seconds: POLL_MS / 1000 }) : d.notDetected}
          </p>
        </section>
      )}

      {searched && shownCount === 0 && (
        <div className="mt-8">
          <EmptyState
            title={d.noSearchResultsTitle}
            body={fmt(d.noSearchResultsBody, { q: query.trim() })}
            action={
              <button
                type="button"
                onClick={resetSearch}
                className="inline-flex min-h-[44px] items-center justify-center rounded-lg border border-edge px-4 py-2 text-sm font-medium text-fg hover:bg-edge focus-visible:outline-2 focus-visible:outline-brand"
              >
                {d.searchReset}
              </button>
            }
          />
        </div>
      )}

      {inBot.length === 0 && !hasSnapshot && (
        <div className="mt-8">
          <EmptyState title={d.botEmptyTitle} body={d.botEmptyBody} />
        </div>
      )}
    </>
  );
}
