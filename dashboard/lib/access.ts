import { createHash, timingSafeEqual } from "node:crypto";
import { cache } from "react";
import { NextResponse } from "next/server";
import { auth } from "@/auth";
import type { Session } from "next-auth";
import { canManage, fetchUserGuilds as fetchUserGuildsRaw } from "@/lib/discord";
import { DISCORD_ID_RE } from "@/lib/validate";
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
 * Cache daftar guild yang bisa dikelola user, keyed by sha256(accessToken).
 * Token mentah TIDAK disimpan — hanya hash-nya sebagai kunci Map.
 * TTL 90 detik: mengurangi panggilan /users/@me/guilds ke Discord API
 * (mis. polling /api/sync-status dari client tiap beberapa detik) tanpa
 * menambah risiko 429.
 *
 * Trade-off yang disengaja:
 * - Undangan ke server baru yang memberi user izin Kelola Server maksimal
 *   terdeteksi 90 detik lebih lambat (sampai cache kedaluwarsa).
 * - Deteksi instalasi/pencopotan BOT tidak terpengaruh: itu dibaca dari
 *   snapshot ingest bot (tabel snapshot di DB), bukan dari daftar guild
 *   user ini.
 * - Cache ini lintas-request (per instance server); beda user = beda hash
 *   token, jadi tidak ada kebocoran antar user.
 */
const MANAGEABLE_TTL_MS = 90_000;
const manageableCache = new Map<string, { ids: Set<string>; ts: number }>();

async function fetchManageableGuildIds(token: string): Promise<Set<string>> {
  const key = createHash("sha256").update(token).digest("hex");
  const hit = manageableCache.get(key);
  if (hit && Date.now() - hit.ts < MANAGEABLE_TTL_MS) return hit.ids;
  const guilds = await fetchUserGuilds(token);
  const ids = new Set(guilds.filter((g) => canManage(g)).map((g) => g.id));
  // Prune entri kedaluwarsa + batasi ukuran agar Map tak tumbuh tanpa batas
  // (mis. token-token lama yang tak pernah dipakai lagi).
  const now = Date.now();
  for (const [k, v] of manageableCache) {
    if (now - v.ts >= MANAGEABLE_TTL_MS) manageableCache.delete(k);
  }
  manageableCache.set(key, { ids, ts: now });
  if (manageableCache.size > 1000) {
    const oldest = [...manageableCache.entries()].sort((a, b) => a[1].ts - b[1].ts)[0]?.[0];
    if (oldest) manageableCache.delete(oldest);
  }
  return ids;
}

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
  // Fail-closed: secret wajib ada dan minimal 32 karakter (sesuai .env.example).
  // Tanpa guard ini, secret lemah yang tidak sengaja dipakai akan lolos diam-diam.
  if (!secret || secret.length < 32) {
    console.error("[auth] DASHBOARD_SECRET tidak valid/terlalu pendek");
    return false;
  }
  const header = req.headers.get("authorization") ?? "";
  const given = header.startsWith("Bearer ") ? header.slice(7) : "";
  const a = Buffer.from(given);
  const b = Buffer.from(secret);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * ID Discord owner bot dari env BOT_OWNER_IDS (dipisah koma).
 * Server-side saja — JANGAN pernah pakai prefix NEXT_PUBLIC_ untuk ini.
 * Entri yang bukan snowflake Discord valid dibuang (fail-closed).
 */
export function botOwnerIds(): string[] {
  const raw = process.env.BOT_OWNER_IDS ?? "";
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter((s) => DISCORD_ID_RE.test(s));
}

/** Discord ID user yang sedang login (dari sesi), atau null. */
export async function getSessionDiscordId(): Promise<string | null> {
  const session = await getSessionSafe();
  return session?.discordId ?? null;
}

/**
 * Pastikan user login dan termasuk owner bot (BOT_OWNER_IDS).
 * Kembalikan null bila lolos, atau NextResponse error bila tidak.
 * Fail-closed: daftar owner kosong = semua ditolak 403.
 * Urutan sama seperti requireManager: autentikasi (401) dulu,
 * baru ketersediaan DB (503), baru otorisasi (403).
 */
export async function requireBotOwner(): Promise<NextResponse | null> {
  const discordId = await getSessionDiscordId();
  if (!discordId) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  if (!botOwnerIds().includes(discordId)) {
    return NextResponse.json({ error: "forbidden" }, { status: 403 });
  }
  return null;
}

/**
 * Pastikan user login dan punya izin Kelola Server di guild.
 * Kembalikan null bila lolos, atau NextResponse error bila tidak.
 */
export async function requireManager(guildId: string): Promise<NextResponse | null> {
  // E-S06 defense-in-depth: ID Discord hanya digit 5..25. Tolak lebih awal
  // (400) di satu titik ini agar string aneh (mis. "../", wildcard) tak
  // pernah sampai ke fetch Discord API atau query DB di semua route guild.
  if (!DISCORD_ID_RE.test(guildId)) {
    return NextResponse.json({ error: "invalid_guild_id" }, { status: 400 });
  }
  // Urutan disengaja: autentikasi dulu, baru ketersediaan DB. Pemanggil
  // tanpa sesi selalu mendapat 401 (bukan 503) — status yang benar untuk
  // "belum login", terlepas dari kondisi database.
  const session = await getSessionSafe();
  const token = session?.accessToken;
  // 401 = belum login; 403 = login tapi bukan manager guild ini.
  // (Sebelumnya keduanya 403 — client tak bisa membedakan "sesi habis"
  // dari "tidak berhak", mis. untuk mengajak login ulang.)
  if (!token) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  try {
    // A-003: daftar guild manageable di-cache 90 detik per hash token
    // (lihat fetchManageableGuildIds) agar polling client tidak menghantam
    // Discord API tiap request.
    const ids = await fetchManageableGuildIds(token);
    if (!ids.has(guildId)) {
      return NextResponse.json({ error: "forbidden" }, { status: 403 });
    }
  } catch {
    return NextResponse.json({ error: "discord_unavailable" }, { status: 502 });
  }
  return null;
}
