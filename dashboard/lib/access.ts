import { timingSafeEqual } from "node:crypto";
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import { canManage, fetchUserGuilds } from "@/lib/discord";
import { dbConfigured } from "@/lib/db";

/** Cek Bearer DASHBOARD_SECRET untuk bot. */
export function botAuthorized(req: Request): boolean {
  const secret = process.env.DASHBOARD_SECRET;
  if (!secret) return false;
  const header = req.headers.get("authorization") ?? "";
  const given = header.startsWith("Bearer ") ? header.slice(7) : "";
  const a = Buffer.from(given);
  const b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * Pastikan user login dan punya izin Kelola Server di guild.
 * Kembalikan null bila lolos, atau NextResponse error bila tidak.
 */
export async function requireManager(guildId: string): Promise<NextResponse | null> {
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const session = await auth();
  const token = session?.accessToken;
  if (!token) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  try {
    const guilds = await fetchUserGuilds(token);
    if (!guilds.some((g) => g.id === guildId && canManage(g))) {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
  } catch {
    return NextResponse.json({ error: "discord_unavailable" }, { status: 502 });
  }
  return null;
}

/** Pastikan ada sesi login (untuk halaman publik seperti leaderboard). */
export async function requireSession(): Promise<NextResponse | null> {
  const session = await auth();
  if (!session) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  return null;
}
