import { NextResponse } from "next/server";
import { sql } from "@vercel/postgres";

export function dbConfigured(): boolean {
  return Boolean(process.env.POSTGRES_URL);
}

const RELATION_MISSING_RE = /relation .* does not exist/i;

/** true bila error = tabel belum dibuat (dashboard/schema.sql belum dijalankan). */
export function isSchemaMissingError(e: unknown): boolean {
  return e instanceof Error && RELATION_MISSING_RE.test(e.message);
}

/**
 * Bungkus handler route API agar query ke tabel yang belum ada
 * (schema.sql belum dijalankan di Postgres) dijawab 503 terstruktur
 * { error: "schema_not_ready", hint } — bukan 500 mentah.
 * Error lain dilempar ulang seperti semula (perilaku tak berubah).
 *
 * Pakai: `export const GET = withDbError(async function GET(...) {...})`.
 */
export function withDbError<T extends (...args: never[]) => Promise<NextResponse>>(
  handler: T,
): T {
  return (async (...args: Parameters<T>): Promise<NextResponse> => {
    try {
      return await handler(...args);
    } catch (e) {
      if (isSchemaMissingError(e)) {
        return NextResponse.json(
          {
            error: "schema_not_ready",
            hint: "Tabel database belum ada — jalankan dashboard/schema.sql sekali di database Postgres.",
          },
          { status: 503 },
        );
      }
      throw e;
    }
  }) as T;
}

export async function latestSnapshot(): Promise<SnapshotPayload | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1`;
  return (rows[0]?.payload as SnapshotPayload) ?? null;
}

/** Cari channel pada snapshot terbaru dan batasi pencarian ke guild yang diminta. */
export async function getSnapshotChannel(
  guildId: string,
  channelId: string,
): Promise<SnapshotChannel | null> {
  const snapshot = await latestSnapshot();
  const guild = snapshot?.guilds.find((item) => item.id === guildId);
  return guild?.channels.find((channel) => channel.id === channelId) ?? null;
}

export async function saveSnapshot(payload: SnapshotPayload): Promise<void> {
  await sql`INSERT INTO snapshots (payload) VALUES (${JSON.stringify(payload)}::jsonb)`;
  await sql`DELETE FROM snapshots WHERE id NOT IN (SELECT id FROM snapshots ORDER BY id DESC LIMIT 24)`;
}

export async function getStoredSettings(guildId: string): Promise<Record<string, unknown>> {
  if (!dbConfigured()) return {};
  const { rows } = await sql`SELECT settings FROM guild_settings WHERE guild_id = ${guildId}`;
  return (rows[0]?.settings as Record<string, unknown>) ?? {};
}

export async function putStoredSettings(guildId: string, settings: Record<string, unknown>): Promise<void> {
  await sql`
    INSERT INTO guild_settings (guild_id, settings, updated_at)
    VALUES (${guildId}, ${JSON.stringify(settings)}::jsonb, NOW())
    ON CONFLICT (guild_id) DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
  `;
}

/**
 * Gabung parsial settings secara ATOMIK di Postgres (operator jsonb ||).
 * Menggantikan pola read-modify-write di JS (getStoredSettings lalu
 * putStoredSettings({...stored, ...clean})) yang rawan race: dua PUT
 * bersamaan bisa saling menimpa dan menghilangkan perubahan salah satu.
 * Baris yang belum ada di-INSERT dulu dengan settings awal {}.
 */
export async function mergeStoredSettings(guildId: string, settings: Record<string, unknown>): Promise<void> {
  await sql`
    INSERT INTO guild_settings (guild_id, settings, updated_at)
    VALUES (${guildId}, ${JSON.stringify(settings)}::jsonb, NOW())
    ON CONFLICT (guild_id) DO UPDATE
    SET settings = guild_settings.settings || EXCLUDED.settings, updated_at = NOW()
  `;
}

export interface SnapshotChannel {
  id: string;
  name: string;
  type: number;
}

export interface SnapshotRole {
  id: string;
  name: string;
}

export interface SnapshotModLogEntry {
  user_id: string;
  user_name: string;
  mod_id: string;
  mod_name: string;
  aksi: string;
  alasan: string;
  waktu: string;
}

export interface SnapshotGuild {
  id: string;
  name: string;
  icon: string | null;
  member_count: number;
  channels: SnapshotChannel[];
  roles: SnapshotRole[];
  leaderboards: {
    levels: { user_id: string; name: string; level: number; xp: number }[];
    coins: { user_id: string; name: string; coins: number }[];
  };
  giveaways: {
    id: number;
    channel_id: string;
    prize: string;
    winners: number;
    ends_at: string;
    participants: number;
  }[];
  /** 25 aksi moderasi terakhir yang dikirim bot; dibaca halaman Mod Log. */
  modlog: SnapshotModLogEntry[];
}

export interface SnapshotPayload {
  bot_name: string;
  guilds: SnapshotGuild[];
  pushed_at: string;
}

export interface SelfRole {
  id: number;
  guild_id: string;
  message_id: string;
  emoji: string;
  role_id: string;
}

export interface AutoResponse {
  id: number;
  guild_id: string;
  trigger: string;
  response: string;
}

export interface GiveawayRequest {
  id: number;
  guild_id: string;
  channel_id: string;
  prize: string;
  winners: number;
  duration_minutes: number;
  status: string;
  note: string;
  created_at: string;
}

export async function getSelfRoles(guildId: string): Promise<SelfRole[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM selfroles WHERE guild_id = ${guildId} ORDER BY id LIMIT 200`;
  return rows as SelfRole[];
}

export async function addSelfRole(guildId: string, messageId: string, emoji: string, roleId: string): Promise<void> {
  await sql`INSERT INTO selfroles (guild_id, message_id, emoji, role_id)
    VALUES (${guildId}, ${messageId}, ${emoji}, ${roleId})
    ON CONFLICT (guild_id, message_id, emoji) DO UPDATE SET role_id = EXCLUDED.role_id`;
}

export async function deleteSelfRole(guildId: string, messageId: string, emoji: string): Promise<void> {
  await sql`DELETE FROM selfroles WHERE guild_id = ${guildId} AND message_id = ${messageId} AND emoji = ${emoji}`;
}

export async function getAutoResponses(guildId: string): Promise<AutoResponse[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM autoresponses WHERE guild_id = ${guildId} ORDER BY id`;
  return rows as AutoResponse[];
}

export async function addAutoResponse(guildId: string, trigger: string, response: string): Promise<void> {
  await sql`INSERT INTO autoresponses (guild_id, trigger, response)
    VALUES (${guildId}, ${trigger}, ${response})
    ON CONFLICT (guild_id, trigger) DO UPDATE SET response = EXCLUDED.response`;
}

export async function deleteAutoResponse(guildId: string, id: number): Promise<void> {
  await sql`DELETE FROM autoresponses WHERE guild_id = ${guildId} AND id = ${id}`;
}

export async function deleteAutoResponseByTrigger(guildId: string, trigger: string): Promise<void> {
  await sql`DELETE FROM autoresponses WHERE guild_id = ${guildId} AND trigger = ${trigger}`;
}

export async function getGiveawayRequests(guildId: string): Promise<GiveawayRequest[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM giveaway_requests WHERE guild_id = ${guildId} ORDER BY id DESC LIMIT 20`;
  return rows as GiveawayRequest[];
}

export async function addGiveawayRequest(
  guildId: string,
  channelId: string,
  prize: string,
  winners: number,
  durationMinutes: number,
): Promise<void> {
  await sql`INSERT INTO giveaway_requests (guild_id, channel_id, prize, winners, duration_minutes)
    VALUES (${guildId}, ${channelId}, ${prize}, ${winners}, ${durationMinutes})`;
}

export async function ackGiveawayRequest(
  id: number,
  guildId: string,
  status: "done" | "failed",
  note: string,
): Promise<void> {
  await sql`UPDATE giveaway_requests SET status = ${status}, note = ${note} WHERE id = ${id} AND guild_id = ${guildId}`;
}

/** Normalisasi nilai tanggal dari postgres ke ISO string (atau null). */
function toIso(v: unknown): string | null {
  if (v === null || v === undefined) return null;
  if (v instanceof Date) return v.toISOString();
  const d = new Date(v as string);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

export interface EmbedField {
  name: string;
  value: string;
  inline?: boolean;
}

export interface EmbedRequest {
  id: number;
  guild_id: string;
  channel_id: string;
  title: string;
  description: string;
  color: string;
  fields: EmbedField[];
  footer: string;
  image_url: string;
  thumbnail_url: string;
  status: string;
  note: string;
  created_at: string;
}

export interface EmbedRequestData {
  guildId: string;
  channelId: string;
  title: string;
  description: string;
  color: string;
  fields: EmbedField[];
  footer: string;
  imageUrl: string;
  thumbnailUrl: string;
}

export async function createEmbedRequest(data: EmbedRequestData): Promise<number> {
  const { rows } = await sql`
    INSERT INTO embed_requests (guild_id, channel_id, title, description, color, fields, footer, image_url, thumbnail_url)
    VALUES (${data.guildId}, ${data.channelId}, ${data.title}, ${data.description}, ${data.color},
      ${JSON.stringify(data.fields)}::jsonb, ${data.footer}, ${data.imageUrl}, ${data.thumbnailUrl})
    RETURNING id`;
  return rows[0].id as number;
}

export async function listEmbedRequests(guildId: string, limit = 20): Promise<EmbedRequest[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM embed_requests WHERE guild_id = ${guildId} ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({
    id: r.id as number,
    guild_id: r.guild_id as string,
    channel_id: r.channel_id as string,
    title: r.title as string,
    description: r.description as string,
    color: r.color as string,
    fields: (Array.isArray(r.fields) ? r.fields : []) as EmbedField[],
    footer: r.footer as string,
    image_url: r.image_url as string,
    thumbnail_url: r.thumbnail_url as string,
    status: r.status as string,
    note: r.note as string,
    created_at: toIso(r.created_at) ?? "",
  }));
}

export async function ackEmbedRequest(
  id: number,
  guildId: string,
  status: "done" | "failed",
  note: string,
): Promise<void> {
  await sql`UPDATE embed_requests SET status = ${status}, note = ${note} WHERE id = ${id} AND guild_id = ${guildId}`;
}

export interface Announcement {
  id: number;
  guild_id: string;
  channel_id: string;
  message: string;
  run_at: string | null;
  interval_minutes: number | null;
  enabled: boolean;
  last_sent_at: string | null;
  created_at: string;
}

export interface AnnouncementData {
  guildId: string;
  channelId: string;
  message: string;
  runAt: string | null;
  intervalMinutes: number | null;
}

export interface AnnouncementPatch {
  message?: string;
  channelId?: string;
  runAt?: string | null;
  intervalMinutes?: number | null;
  enabled?: boolean;
}

export async function createAnnouncement(data: AnnouncementData): Promise<number> {
  const { rows } = await sql`
    INSERT INTO announcements (guild_id, channel_id, message, run_at, interval_minutes)
    VALUES (${data.guildId}, ${data.channelId}, ${data.message}, ${data.runAt}, ${data.intervalMinutes})
    RETURNING id`;
  return rows[0].id as number;
}

export async function listAnnouncements(guildId: string): Promise<Announcement[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM announcements WHERE guild_id = ${guildId} ORDER BY id DESC LIMIT 50`;
  return rows.map((r) => ({
    id: r.id as number,
    guild_id: r.guild_id as string,
    channel_id: r.channel_id as string,
    message: r.message as string,
    run_at: toIso(r.run_at),
    interval_minutes: r.interval_minutes as number | null,
    enabled: r.enabled as boolean,
    last_sent_at: toIso(r.last_sent_at),
    created_at: toIso(r.created_at) ?? "",
  }));
}

/** Catat waktu pengiriman dari bot hanya untuk pengumuman milik guild yang sama. */
export async function markAnnouncementSent(
  id: number,
  guildId: string,
  lastSentAt: string,
): Promise<boolean> {
  const { rows } = await sql`
    UPDATE announcements
    SET last_sent_at = GREATEST(
      COALESCE(last_sent_at, ${lastSentAt}::timestamptz),
      ${lastSentAt}::timestamptz
    )
    WHERE id = ${id} AND guild_id = ${guildId}
    RETURNING id
  `;
  return rows.length > 0;
}

export async function updateAnnouncement(
  id: number,
  guildId: string,
  patch: AnnouncementPatch,
): Promise<boolean> {
  // true bila baris (id + guild_id) benar-benar ada & ter-update; route
  // memakai ini untuk menjawab 404, bukan 200 semu, saat id/guild tak cocok.
  let ditemukan = false;
  if (patch.message !== undefined) {
    const { rows } = await sql`UPDATE announcements SET message = ${patch.message} WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
    ditemukan ||= rows.length > 0;
  }
  if (patch.channelId !== undefined) {
    const { rows } = await sql`UPDATE announcements SET channel_id = ${patch.channelId} WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
    ditemukan ||= rows.length > 0;
  }
  if (patch.runAt !== undefined) {
    const { rows } = await sql`UPDATE announcements SET run_at = ${patch.runAt} WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
    ditemukan ||= rows.length > 0;
  }
  if (patch.intervalMinutes !== undefined) {
    const { rows } = await sql`UPDATE announcements SET interval_minutes = ${patch.intervalMinutes} WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
    ditemukan ||= rows.length > 0;
  }
  if (patch.enabled !== undefined) {
    const { rows } = await sql`UPDATE announcements SET enabled = ${patch.enabled} WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
    ditemukan ||= rows.length > 0;
  }
  return ditemukan;
}

export async function deleteAnnouncement(id: number, guildId: string): Promise<boolean> {
  const { rows } = await sql`DELETE FROM announcements WHERE id = ${id} AND guild_id = ${guildId} RETURNING id`;
  return rows.length > 0;
}

/** Jumlah pengumuman aktif (enabled) milik guild — untuk cek kuota tier. */
export async function countActiveAnnouncements(guildId: string): Promise<number> {
  if (!dbConfigured()) return 0;
  const { rows } = await sql`SELECT COUNT(*) AS count FROM announcements WHERE guild_id = ${guildId} AND enabled = TRUE`;
  return Number(rows[0]?.count ?? 0);
}

/**
 * Buat pengumuman HANYA bila kuota aktif guild belum penuh — SATU statement
 * atomik (INSERT ... SELECT ... WHERE count < limit), jadi dua POST
 * bersamaan tidak bisa sama-sama lolos melewati batas. Kembalikan id baru,
 * atau null bila kuota penuh. Pengumuman dibuat enabled (DEFAULT TRUE di
 * skema, kolom enabled tidak disebut) sehingga langsung terhitung aktif.
 */
export async function createAnnouncementWithQuota(
  data: AnnouncementData,
  limit: number,
): Promise<number | null> {
  const { rows } = await sql`
    INSERT INTO announcements (guild_id, channel_id, message, run_at, interval_minutes)
    SELECT ${data.guildId}, ${data.channelId}, ${data.message},
      ${data.runAt}::timestamptz, ${data.intervalMinutes}
    WHERE (SELECT COUNT(*) FROM announcements WHERE guild_id = ${data.guildId} AND enabled = TRUE) < ${limit}
    RETURNING id`;
  return (rows[0]?.id as number | undefined) ?? null;
}

// ---------------------------------------------------------------------------
// Entitlement Free/VIP per guild (guild_entitlements + entitlement_audit_log)
// ---------------------------------------------------------------------------

export interface GuildEntitlement {
  guild_id: string;
  tier: string;
  status: string;
  source: string;
  starts_at: string | null;
  expires_at: string | null;
  provider_entitlement_id: string | null;
  provider_subscription_id: string | null;
  granted_by: string | null;
  note: string | null;
  bot_present: boolean;
  first_seen_at: string | null;
  last_seen_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface EntitlementAuditRow {
  id: number;
  guild_id: string;
  actor_id: string | null;
  action: string;
  tier_before: string | null;
  tier_after: string | null;
  status_before: string | null;
  status_after: string | null;
  expires_before: string | null;
  expires_after: string | null;
  reason: string | null;
  created_at: string | null;
}

/** Petakan baris mentah guild_entitlements ke objek bertanggal ISO. */
function mapEntitlementRow(r: Record<string, unknown>): GuildEntitlement {
  return {
    guild_id: r.guild_id as string,
    tier: r.tier as string,
    status: r.status as string,
    source: r.source as string,
    starts_at: toIso(r.starts_at),
    expires_at: toIso(r.expires_at),
    provider_entitlement_id: (r.provider_entitlement_id as string | null) ?? null,
    provider_subscription_id: (r.provider_subscription_id as string | null) ?? null,
    granted_by: (r.granted_by as string | null) ?? null,
    note: (r.note as string | null) ?? null,
    bot_present: Boolean(r.bot_present),
    first_seen_at: toIso(r.first_seen_at),
    last_seen_at: toIso(r.last_seen_at),
    created_at: toIso(r.created_at),
    updated_at: toIso(r.updated_at),
  };
}

export async function getEntitlement(guildId: string): Promise<GuildEntitlement | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT * FROM guild_entitlements WHERE guild_id = ${guildId}`;
  return rows[0] ? mapEntitlementRow(rows[0] as Record<string, unknown>) : null;
}

/**
 * Daftarkan guild yang terlihat bot (dari ingest) tanpa menyentuh
 * tier/status/source/expiry sama sekali: guild baru masuk sebagai free
 * (DEFAULT skema), guild lama hanya diperbarui bot_present/last_seen_at.
 * Satu statement per guild.
 */
export async function registerGuildsSeen(
  guilds: { id: string; name?: string }[],
): Promise<void> {
  for (const g of guilds) {
    await sql`
      INSERT INTO guild_entitlements (guild_id) VALUES (${g.id})
      ON CONFLICT (guild_id) DO UPDATE
      SET bot_present = TRUE, last_seen_at = NOW(), updated_at = NOW()
    `;
  }
}

/** Buat baris entitlement free bila belum ada (lazy register saat sync), lalu baca. */
export async function ensureEntitlement(guildId: string): Promise<GuildEntitlement | null> {
  if (!dbConfigured()) return null;
  await sql`
    INSERT INTO guild_entitlements (guild_id) VALUES (${guildId})
    ON CONFLICT (guild_id) DO NOTHING
  `;
  return getEntitlement(guildId);
}

/**
 * Semua entitlement, terbaru diubah dulu, maks 200.
 * Filter `q` (bila ada) diterapkan sebagai LIKE pada guild_id; pencocokan
 * nama guild diselesaikan route dari snapshot terbaru.
 */
export async function listEntitlements(q?: string): Promise<GuildEntitlement[]> {
  if (!dbConfigured()) return [];
  if (q) {
    const like = `%${q}%`;
    const { rows } = await sql`SELECT * FROM guild_entitlements WHERE guild_id LIKE ${like} ORDER BY updated_at DESC LIMIT 200`;
    return rows.map((r) => mapEntitlementRow(r as Record<string, unknown>));
  }
  const { rows } = await sql`SELECT * FROM guild_entitlements ORDER BY updated_at DESC LIMIT 200`;
  return rows.map((r) => mapEntitlementRow(r as Record<string, unknown>));
}

export async function listEntitlementAudit(
  guildId: string,
  limit = 50,
): Promise<EntitlementAuditRow[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM entitlement_audit_log WHERE guild_id = ${guildId} ORDER BY id DESC LIMIT ${limit}`;
  return rows.map((r) => ({
    id: Number(r.id),
    guild_id: r.guild_id as string,
    actor_id: (r.actor_id as string | null) ?? null,
    action: r.action as string,
    tier_before: (r.tier_before as string | null) ?? null,
    tier_after: (r.tier_after as string | null) ?? null,
    status_before: (r.status_before as string | null) ?? null,
    status_after: (r.status_after as string | null) ?? null,
    expires_before: toIso(r.expires_before),
    expires_after: toIso(r.expires_after),
    reason: (r.reason as string | null) ?? null,
    created_at: toIso(r.created_at),
  }));
}

export type EntitlementAction = "grant" | "extend" | "revoke";

export interface EntitlementMutationInput {
  guildId: string;
  action: EntitlementAction;
  durationDays: number | null;
  reason?: string | null;
  actorId: string | null;
  source?: string;
}

const DAY_MS = 24 * 60 * 60 * 1000;

/**
 * Terapkan grant/extend/revoke ke entitlement guild dan tulis audit log.
 *
 * State baru dihitung di TS dari baris lama:
 * - grant: tier vip, status active, starts_at = sekarang,
 *   expires_at = sekarang + durationDays hari (null duration = permanen),
 *   granted_by = actor, note = reason.
 * - extend: bila baris lama bertier vip, expires_at baru =
 *   max(expires_at lama, sekarang) + durationDays hari (expires null =
 *   permanen, dibiarkan null); status diaktifkan lagi, granted_by diperbarui.
 *   Bila baris free / belum ada, extend DIPERLAKUKAN SEPERTI GRANT dengan
 *   durasi itu (tidak ada masa vip yang bisa diperpanjang).
 * - revoke: hanya status menjadi 'revoked'; tier & expiry dibiarkan agar
 *   riwayat pemberian tetap terlihat.
 *
 * Penulisan baris utama SATU statement (INSERT ... ON CONFLICT DO UPDATE
 * ... RETURNING *), lalu audit log statement kedua. Tanpa helper transaksi
 * di db.ts, keduanya TIDAK atomik penuh: crash di antara keduanya bisa
 * menyisakan baris berubah tanpa audit (urutan disengaja row dulu, audit
 * sesudahnya — audit hilang lebih dapat diterima daripada audit untuk
 * perubahan yang tidak pernah terjadi).
 */
export async function applyEntitlementMutation(
  input: EntitlementMutationInput,
): Promise<GuildEntitlement | null> {
  if (!dbConfigured()) return null;
  const { guildId, action, durationDays, actorId } = input;
  const source = input.source ?? "owner_grant";
  const reason = input.reason ? input.reason.slice(0, 200) : null;
  const before = await getEntitlement(guildId);
  const now = new Date();

  let tier = before?.tier ?? "free";
  let status = before?.status ?? "active";
  let rowSource = before?.source ?? "default";
  let startsAt: string | null = before?.starts_at ?? null;
  let expiresAt: string | null = before?.expires_at ?? null;
  let grantedBy: string | null = before?.granted_by ?? null;
  let note: string | null = before?.note ?? null;

  if (action === "grant" || (action === "extend" && before?.tier !== "vip")) {
    tier = "vip";
    status = "active";
    rowSource = source;
    startsAt = now.toISOString();
    expiresAt = durationDays ? new Date(now.getTime() + durationDays * DAY_MS).toISOString() : null;
    grantedBy = actorId;
    note = reason;
  } else if (action === "extend") {
    // Di sini before pasti ada dan tier-nya vip.
    tier = "vip";
    status = "active";
    rowSource = source;
    grantedBy = actorId;
    if (reason) note = reason;
    if (durationDays && expiresAt) {
      const base = Math.max(new Date(expiresAt).getTime(), now.getTime());
      expiresAt = new Date(base + durationDays * DAY_MS).toISOString();
    } else if (durationDays && !expiresAt) {
      // VIP permanen (expires null): tidak ada yang diperpanjang, tetap permanen.
      expiresAt = null;
    }
    if (!startsAt) startsAt = now.toISOString();
  } else if (action === "revoke") {
    status = "revoked";
  }

  const { rows } = await sql`
    INSERT INTO guild_entitlements
      (guild_id, tier, status, source, starts_at, expires_at, granted_by, note)
    VALUES (${guildId}, ${tier}, ${status}, ${rowSource}, ${startsAt}, ${expiresAt}, ${grantedBy}, ${note})
    ON CONFLICT (guild_id) DO UPDATE SET
      tier = EXCLUDED.tier,
      status = EXCLUDED.status,
      source = EXCLUDED.source,
      starts_at = EXCLUDED.starts_at,
      expires_at = EXCLUDED.expires_at,
      granted_by = EXCLUDED.granted_by,
      note = EXCLUDED.note,
      updated_at = NOW()
    RETURNING *
  `;
  const after = rows[0] ? mapEntitlementRow(rows[0] as Record<string, unknown>) : null;

  await sql`
    INSERT INTO entitlement_audit_log
      (guild_id, actor_id, action, tier_before, tier_after, status_before, status_after, expires_before, expires_after, reason)
    VALUES (${guildId}, ${actorId}, ${action},
      ${before?.tier ?? null}, ${tier},
      ${before?.status ?? null}, ${status},
      ${before?.expires_at ?? null}, ${expiresAt}, ${reason})
  `;
  return after;
}
