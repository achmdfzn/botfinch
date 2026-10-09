import { NextResponse } from "next/server";
import { dbConfigured, saveSnapshot, type SnapshotGuild, type SnapshotPayload } from "@/lib/db";
import { botAuthorized } from "@/lib/access";

function sanitizeLeaderboards(v: unknown): SnapshotGuild["leaderboards"] {
  const empty = { levels: [], coins: [] };
  if (!v || typeof v !== "object") return empty;
  const o = v as Record<string, unknown>;
  const pick = (arr: unknown, fields: string[]) =>
    Array.isArray(arr)
      ? arr
          .filter((e) => e && typeof (e as Record<string, unknown>).user_id === "string")
          .slice(0, 25)
          .map((e) => {
            const r = e as Record<string, unknown>;
            const out: Record<string, unknown> = {
              user_id: r.user_id as string,
              name: typeof r.name === "string" ? (r.name as string).slice(0, 50) : "?",
            };
            for (const f of fields) {
              const n = r[f];
              out[f] = Number.isFinite(n) ? Math.max(0, Math.floor(n as number)) : 0;
            }
            return out;
          })
      : [];
  return {
    levels: pick(o.levels, ["level", "xp"]) as SnapshotGuild["leaderboards"]["levels"],
    coins: pick(o.coins, ["coins"]) as SnapshotGuild["leaderboards"]["coins"],
  };
}

function sanitizeGiveaways(v: unknown): SnapshotGuild["giveaways"] {
  if (!Array.isArray(v)) return [];
  return v
    .filter((e) => e && Number.isFinite((e as Record<string, unknown>).id))
    .slice(0, 25)
    .map((e) => {
      const r = e as Record<string, unknown>;
      return {
        id: Math.floor(r.id as number),
        channel_id: typeof r.channel_id === "string" ? (r.channel_id as string).slice(0, 32) : "",
        prize: typeof r.prize === "string" ? (r.prize as string).slice(0, 100) : "",
        winners: Number.isFinite(r.winners) ? Math.max(1, Math.floor(r.winners as number)) : 1,
        ends_at: typeof r.ends_at === "string" ? (r.ends_at as string).slice(0, 32) : "",
        participants: Number.isFinite(r.participants) ? Math.max(0, Math.floor(r.participants as number)) : 0,
      };
    });
}

function sanitizeModlog(v: unknown): SnapshotGuild["modlog"] {
  if (!Array.isArray(v)) return [];
  const str = (x: unknown, max: number) => (typeof x === "string" ? (x as string).slice(0, max) : "");
  return v
    .filter((e) => e && typeof (e as Record<string, unknown>).user_id === "string")
    .slice(0, 25)
    .map((e) => {
      const r = e as Record<string, unknown>;
      return {
        user_id: str(r.user_id, 32),
        user_name: str(r.user_name, 50),
        mod_id: str(r.mod_id, 32),
        mod_name: str(r.mod_name, 50),
        aksi: str(r.aksi, 30),
        alasan: str(r.alasan, 500),
        waktu: str(r.waktu, 40),
      };
    });
}

export async function POST(req: Request) {
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  let body: SnapshotPayload;
  try {
    body = (await req.json()) as SnapshotPayload;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
  if (!body || !Array.isArray(body.guilds)) {
    return NextResponse.json({ error: "invalid_payload" }, { status: 400 });
  }
  const guilds = body.guilds
    .filter((g) => g && typeof g.id === "string")
    .slice(0, 500)
    .map((g) => {
      const raw = g as unknown as Record<string, unknown>;
      return {
        id: g.id,
        name: typeof g.name === "string" ? g.name.slice(0, 100) : g.id,
        icon: typeof g.icon === "string" ? g.icon : null,
        member_count: Number.isFinite(g.member_count) ? Math.max(0, Math.floor(g.member_count)) : 0,
        channels: Array.isArray(g.channels)
          ? g.channels
              .filter((c) => c && typeof c.id === "string")
              .slice(0, 200)
              .map((c) => ({
                id: c.id,
                name: typeof c.name === "string" ? c.name.slice(0, 100) : c.id,
                type: Number.isFinite(c.type) ? c.type : 0,
              }))
          : [],
        roles: Array.isArray(raw.roles)
          ? (raw.roles as unknown[])
              .filter((r) => r && typeof (r as Record<string, unknown>).id === "string")
              .slice(0, 200)
              .map((r) => {
                const rr = r as Record<string, unknown>;
                return {
                  id: rr.id as string,
                  name: typeof rr.name === "string" ? (rr.name as string).slice(0, 100) : (rr.id as string),
                };
              })
          : [],
        leaderboards: sanitizeLeaderboards(raw.leaderboards),
        giveaways: sanitizeGiveaways(raw.giveaways),
        modlog: sanitizeModlog(raw.modlog),
      };
    });
  await saveSnapshot({
    bot_name: typeof body.bot_name === "string" ? body.bot_name.slice(0, 50) : "Finch",
    guilds,
    pushed_at: new Date().toISOString(),
  });
  return NextResponse.json({ ok: true, guilds: guilds.length });
}
