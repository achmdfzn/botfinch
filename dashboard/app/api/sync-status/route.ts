import { NextResponse } from "next/server";
import { latestSnapshot } from "@/lib/db";
import { fetchUserGuilds, getSessionSafe } from "@/lib/access";
import { canManage } from "@/lib/discord";

export const instant = false;

/**
 * Status ringan untuk auto-refresh daftar server di /dashboard.
 * Mengembalikan guild yang SUDAH ada di snapshot terakhir bot
 * (tanpa memanggil API Discord untuk snapshot — jauh lebih ringan).
 *
 * Hanya guild yang user-nya punya izin Kelola Server yang dikembalikan:
 * tanpa filter ini, user login mana pun bisa memetakan semua server
 * pelanggan bot (enumerasi lintas-guild).
 */
export async function GET() {
  const session = await getSessionSafe();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  let manageable: Set<string>;
  try {
    const guilds = await fetchUserGuilds(token);
    manageable = new Set(guilds.filter((g) => canManage(g)).map((g) => g.id));
  } catch {
    return NextResponse.json({ error: "discord_unavailable" }, { status: 502 });
  }
  const snap = await latestSnapshot();
  return NextResponse.json({
    pushed_at: snap?.pushed_at ?? null,
    guilds: (snap?.guilds ?? [])
      .filter((g) => manageable.has(g.id))
      .map((g) => ({
        id: g.id,
        name: g.name,
        icon: g.icon,
        member_count: g.member_count,
      })),
  });
}
