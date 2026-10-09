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

const POLL_MS = 15_000;
const MAX_POLLS = 20; // ~5 menit lalu berhenti sendiri

/**
 * Daftar server dengan auto-refresh: setiap 15 detik menanyakan
 * /api/sync-status; guild yang baru terdeteksi di snapshot bot langsung
 * pindah ke daftar "Kelola" tanpa reload manual. Berhenti sendiri bila
 * semua guild sudah terdeteksi atau batas waktu tercapai.
 */
export default function GuildListSync({ initialInBot, initialNotInBot, initialHasSnapshot }: Props) {
  const { dict, lang } = useI18n();
  const d = dict.dashboard;
  const locale = lang === "id" ? "id-ID" : "en-US";
  const [inBot, setInBot] = useState<GuildLite[]>(initialInBot);
  const [notInBot, setNotInBot] = useState<GuildLite[]>(initialNotInBot);
  const [hasSnapshot, setHasSnapshot] = useState(initialHasSnapshot);
  const [checking, setChecking] = useState(initialNotInBot.length > 0);
  // ref agar closure interval selalu baca daftar pending terbaru
  const pendingRef = useRef<GuildLite[]>(initialNotInBot);

  useEffect(() => {
    if (pendingRef.current.length === 0) return;
    let polls = 0;
    const timer = setInterval(async () => {
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
            moved.push({ id: s.id, name: s.name, icon: s.icon, memberCount: s.member_count });
            return false;
          }
          return true;
        });
        if (moved.length > 0) {
          setNotInBot([...pendingRef.current]);
          setInBot((cur) => [...cur, ...moved]);
        }
      }
      if (pendingRef.current.length === 0 || polls >= MAX_POLLS) {
        clearInterval(timer);
        setChecking(false);
      }
    }, POLL_MS);
    return () => clearInterval(timer);
  }, []);

  const memberText = (n: number | null) =>
    n === null ? null : fmt(d.cardMembers, { n: n.toLocaleString(locale) });

  return (
    <>
      <div className="mt-8 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {inBot.map((g) => (
          <GuildCard
            key={g.id}
            id={g.id}
            name={g.name}
            icon={g.icon}
            memberText={memberText(g.memberCount)}
            inBot
            manageLabel={d.cardManage}
            inviteLabel={dict.nav.inviteBot}
            noDataLabel={d.cardNoData}
          />
        ))}
      </div>

      {notInBot.length > 0 && (
        <section className="mt-10" aria-label={d.sectionNotInBot}>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">{d.sectionNotInBot}</h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {notInBot.map((g) => (
              <GuildCard
                key={g.id}
                id={g.id}
                name={g.name}
                icon={g.icon}
                memberText={null}
                inBot={false}
                manageLabel={d.cardManage}
                inviteLabel={dict.nav.inviteBot}
                noDataLabel={d.cardNoData}
              />
            ))}
          </div>
          <p className="mt-4 text-xs text-muted" role="status">
            {checking ? d.checking : d.notDetected}
          </p>
        </section>
      )}

      {inBot.length === 0 && !hasSnapshot && (
        <div className="mt-8">
          <EmptyState title={d.botEmptyTitle} body={d.botEmptyBody} />
        </div>
      )}
    </>
  );
}
