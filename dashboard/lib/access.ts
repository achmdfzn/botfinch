import { timingSafeEqual } from "node:crypto";
import { cache } from "react";
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import type { Session } from "next-auth";
import { canManage, fetchUserGuilds as fetchUserGuildsRaw } from "@/lib/discord";
import { dbConfigured } from "@/lib/db";

/**
 * Daftar guild user dari Discord API, di-dedup per request server via
 * React cache(). Tiap halaman guild memanggil ini 2x (layout + page) dan
 * tiap API call dari client component 1x — tanpa dedup, 3+ request identik
 * ke Discord per pemuatan halaman (risiko 429). Aman karena argumennya
 * accessToken dan cache() bersifat per-request (tidak bocor antar user).
 *
 * Modul ini hanya diimpor kode server (route + server component), jadi
 * cache() dari react aman dipakai di sini.
 */
export const fetchUserGuilds = cache(fetchUserGuildsRaw);

/**
 * auth() yang aman untuk halaman & API: cookie sesi yang rusak/kedaluwarsa
 * (Auth.js melempar JWTSessionError) diperlakukan sebagai "belum login"
 * (null), bukan crash 500. Penyebab umum: AUTH_SECRET berubah setelah
 * cookie dibuat, atau cookie korup di browser.
 */
export async function getSessionSafe(): Promise<Session | null> {
  try {
    return await auth();
  } catch (e) {
    console.warn(
      "[auth] sesi tidak terbaca, dianggap belum login:",
      e instanceof Error ? e.message : e,
    );
    return null;
  }
}

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
  const session = await getSessionSafe();
  const token = session?.accessToken;
  // 401 = belum login; 403 = login tapi bukan manager guild ini.
  // (Sebelumnya keduanya 403 — client tak bisa membedakan "sesi habis"
  // dari "tidak berhak", mis. untuk mengajak login ulang.)
  if (!token) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
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
