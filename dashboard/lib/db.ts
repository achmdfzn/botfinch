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

// ---------------------------------------------------------------------------
// Billing otomatis (billing_orders + billing_webhook_events)
// ---------------------------------------------------------------------------
// Alur: checkout membuat order (status 'created' -> 'pending' setelah info
// provider terpasang), webhook provider yang terverifikasi mengklaim order
// sebagai 'paid' lewat claimBillingOrderPaid (satu statement atomik), lalu
// applyPaymentToEntitlement mengaktifkan / memperpanjang VIP guild.
// Semua SQL parameterized via template `sql`; tidak ada helper transaksi
// di file ini, jadi fungsi multi-statement (order -> audit, entitlement ->
// audit) mengikuti keterbatasan yang sama seperti applyEntitlementMutation:
// statement dijalankan berurutan, BUKAN atomik penuh.

export type BillingOrder = {
  id: number;
  order_ref: string;
  buyer_user_id: string;
  guild_id: string;
  plan_id: string;
  amount_idr: number;
  currency: string;
  duration_days: number;
  status: string;
  provider: string;
  provider_txn_id: string | null;
  provider_redirect_url: string | null;
  created_at: string | null;
  expires_at: string | null;
  paid_at: string | null;
  entitlement_applied_at: string | null;
  updated_at: string | null;
};

// `type` (bukan interface) agar punya implicit index signature — mock dan
// pemanggil generik yang mengetik parameter sebagai Record<string, unknown>
// tetap kompatibel dengan input ini.
export type CreateBillingOrderInput = {
  orderRef: string;
  buyerUserId: string;
  guildId: string;
  planId: string;
  amountIdr: number;
  currency?: string;
  durationDays: number;
  provider: string;
  expiresAt: string;
};

/** Petakan baris mentah billing_orders ke objek bertanggal ISO. */
function mapBillingOrderRow(r: Record<string, unknown>): BillingOrder {
  return {
    id: Number(r.id),
    order_ref: r.order_ref as string,
    buyer_user_id: r.buyer_user_id as string,
    guild_id: r.guild_id as string,
    plan_id: r.plan_id as string,
    amount_idr: Number(r.amount_idr),
    currency: r.currency as string,
    duration_days: Number(r.duration_days),
    status: r.status as string,
    provider: r.provider as string,
    provider_txn_id: (r.provider_txn_id as string | null) ?? null,
    provider_redirect_url: (r.provider_redirect_url as string | null) ?? null,
    created_at: toIso(r.created_at),
    expires_at: toIso(r.expires_at),
    paid_at: toIso(r.paid_at),
    entitlement_applied_at: toIso(r.entitlement_applied_at),
    updated_at: toIso(r.updated_at),
  };
}

/** Buat order billing baru dengan status 'created' dan kembalikan barisnya. */
export async function createBillingOrder(
  input: CreateBillingOrderInput,
): Promise<BillingOrder> {
  const currency = input.currency ?? "IDR";
  const { rows } = await sql`
    INSERT INTO billing_orders
      (order_ref, buyer_user_id, guild_id, plan_id, amount_idr, currency,
       duration_days, status, provider, expires_at)
    VALUES (${input.orderRef}, ${input.buyerUserId}, ${input.guildId},
      ${input.planId}, ${input.amountIdr}, ${currency},
      ${input.durationDays}, 'created', ${input.provider}, ${input.expiresAt})
    RETURNING *
  `;
  return mapBillingOrderRow(rows[0] as Record<string, unknown>);
}

export async function getBillingOrderByRef(
  orderRef: string,
): Promise<BillingOrder | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT * FROM billing_orders WHERE order_ref = ${orderRef} LIMIT 1`;
  return rows[0] ? mapBillingOrderRow(rows[0] as Record<string, unknown>) : null;
}

/**
 * Order aktif terbaru untuk (guild, plan): status 'created'/'pending' dan
 * belum melewati expires_at order-nya. Dipakai mencegah checkout ganda
 * untuk paket yang sama selama order sebelumnya masih bisa dibayar.
 */
export async function findActiveBillingOrder(
  guildId: string,
  planId: string,
): Promise<BillingOrder | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`
    SELECT * FROM billing_orders
    WHERE guild_id = ${guildId} AND plan_id = ${planId}
      AND status IN ('created', 'pending')
      AND expires_at > NOW()
    ORDER BY id DESC
    LIMIT 1
  `;
  return rows[0] ? mapBillingOrderRow(rows[0] as Record<string, unknown>) : null;
}

/** Riwayat order sebuah guild, terbaru dulu. */
export async function listBillingOrders(
  guildId: string,
  limit = 20,
): Promise<BillingOrder[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`
    SELECT * FROM billing_orders
    WHERE guild_id = ${guildId}
    ORDER BY id DESC
    LIMIT ${limit}
  `;
  return rows.map((r) => mapBillingOrderRow(r as Record<string, unknown>));
}

/**
 * Pasang info provider (id transaksi + URL redirect pembayaran) ke order.
 * Status hanya maju 'created' -> 'pending' (kondisional via CASE); order
 * yang sudah di status lain tidak diturunkan. Return true bila baris ada.
 */
export async function setBillingOrderProviderInfo(
  orderRef: string,
  providerTxnId: string | null,
  redirectUrl: string | null,
): Promise<boolean> {
  const { rows } = await sql`
    UPDATE billing_orders
    SET provider_txn_id = ${providerTxnId},
        provider_redirect_url = ${redirectUrl},
        status = CASE WHEN status = 'created' THEN 'pending' ELSE status END,
        updated_at = NOW()
    WHERE order_ref = ${orderRef}
    RETURNING id
  `;
  return rows.length > 0;
}

/**
 * Transisi status order yang dijaga daftar status asal yang diizinkan:
 * UPDATE hanya menyentuh baris bila status saat ini ada di `fromAllowed`.
 * Return false (tanpa perubahan) bila transisi tidak diizinkan / order
 * tidak ada / `fromAllowed` kosong. Inilah penjaga state machine order:
 * status terminal ('failed'/'cancelled') tidak pernah ada di fromAllowed
 * untuk transisi pengaktifan, jadi settlement yang datang sesudahnya
 * tidak bisa mengaktifkan order terminal.
 */
export async function transitionBillingOrder(
  orderRef: string,
  to: string,
  fromAllowed: string[],
): Promise<boolean> {
  if (fromAllowed.length === 0) return false;
  // Template `sql` hanya menerima nilai Primitive (bukan array), jadi
  // daftar status dikirim sebagai SATU parameter string berisi literal
  // array Postgres lalu di-cast ke text[] di SQL. Tiap elemen dikutip
  // dan di-escape mengikuti aturan literal array Postgres.
  const fromArrayLiteral = `{${fromAllowed
    .map((s) => `"${s.replace(/(["\\])/g, "\\$1")}"`)
    .join(",")}}`;
  const { rows } = await sql`
    UPDATE billing_orders
    SET status = ${to}, updated_at = NOW()
    WHERE order_ref = ${orderRef}
      AND status = ANY(${fromArrayLiteral}::text[])
    RETURNING id
  `;
  return rows.length > 0;
}

/**
 * Catat penerimaan webhook provider ke log audit. Return true hanya
 * untuk event yang BARU tercatat; event_key yang sama diterima ulang
 * (retry provider) menghasilkan false lewat ON CONFLICT DO NOTHING.
 * PENTING: log ini BUKAN gerbang dedupe — pemanggil tetap memproses
 * event (retry yang sah bisa membawa status yang lebih baru), dan
 * idempotensi hasil akhir dijamin oleh klaim atomik
 * claimBillingOrderPaid, bukan oleh tabel ini.
 */
export async function recordWebhookEvent(
  provider: string,
  eventKey: string,
  orderRef: string | null,
  providerStatus: string | null,
): Promise<boolean> {
  const { rows } = await sql`
    INSERT INTO billing_webhook_events (provider, event_key, order_ref, provider_status)
    VALUES (${provider}, ${eventKey}, ${orderRef}, ${providerStatus})
    ON CONFLICT (event_key) DO NOTHING
    RETURNING id
  `;
  return rows.length > 0;
}

/**
 * Klaim order sebagai lunas dalam SATU statement atomik: CTE `prev`
 * membaca status lama dari snapshot statement yang sama, lalu UPDATE
 * hanya menang bila paid_at masih NULL (penanda klaim), status bukan
 * terminal ('failed'/'cancelled'/'refunded'/'disputed'), dan penerapan
 * entitlement belum ditandai selesai. Status 'expired' SENGAJA
 * diizinkan: settlement yang terlambat tetap mengaktifkan (late
 * settlement) dan status lamanya ('expired') terbaca di previousStatus
 * untuk diaudit pemanggil.
 *
 * Penanda klaim (paid_at) SENGAJA dipisah dari penanda penerapan
 * (entitlement_applied_at): klaim di-set di sini, sedangkan
 * entitlement_applied_at hanya di-set markBillingOrderApplied SETELAH
 * applyPaymentToEntitlement berhasil. Bila proses mati di antaranya,
 * order berstatus 'paid' dengan entitlement_applied_at NULL — keadaan
 * yang dapat dideteksi dan dipulihkan service pada webhook retry /
 * rekonsiliasi berikutnya (bukan 'already_applied' selamanya).
 * Return null bila klaim kalah: order tidak ada, sudah pernah diklaim,
 * atau status terminal. provider_txn_id tidak menimpa nilai yang sudah
 * terpasang (COALESCE).
 */
export async function claimBillingOrderPaid(
  orderRef: string,
  providerTxnId: string | null,
): Promise<{ order: BillingOrder; previousStatus: string } | null> {
  const { rows } = await sql`
    WITH prev AS (
      SELECT status AS previous_status
      FROM billing_orders
      WHERE order_ref = ${orderRef}
    ),
    updated AS (
      UPDATE billing_orders b
      SET status = 'paid',
          paid_at = NOW(),
          provider_txn_id = COALESCE(b.provider_txn_id, ${providerTxnId}),
          updated_at = NOW()
      FROM prev
      WHERE b.order_ref = ${orderRef}
        AND b.paid_at IS NULL
        AND b.entitlement_applied_at IS NULL
        AND b.status NOT IN ('failed', 'cancelled', 'refunded', 'disputed')
      RETURNING b.*
    )
    SELECT u.*, p.previous_status
    FROM updated u, prev p
  `;
  const row = rows[0] as Record<string, unknown> | undefined;
  if (!row) return null;
  return {
    order: mapBillingOrderRow(row),
    previousStatus: row.previous_status as string,
  };
}

/**
 * Tandai penerapan entitlement order SELESAI — dipanggil service hanya
 * SETELAH applyPaymentToEntitlement berhasil (termasuk outcome
 * noop_permanent / blocked_suspended: keputusan penerapannya final).
 * Kondisional pada entitlement_applied_at yang masih NULL agar retry
 * tidak menimpa penanda pertama. Return true bila baris ditandai.
 */
export async function markBillingOrderApplied(
  orderRef: string,
  providerTxnId: string | null,
): Promise<boolean> {
  const { rows } = await sql`
    UPDATE billing_orders
    SET entitlement_applied_at = NOW(),
        provider_txn_id = COALESCE(provider_txn_id, ${providerTxnId}),
        updated_at = NOW()
    WHERE order_ref = ${orderRef} AND entitlement_applied_at IS NULL
    RETURNING id
  `;
  return rows.length > 0;
}

/**
 * Tutup order aktif yang sudah lewat expires_at menurut jam server
 * tetapi statusnya masih 'created'/'pending' (tidak ada cron di repo
 * ini). Dipakai route checkout sebelum membuat order baru: indeks unik
 * parsial idx_billing_orders_one_active melihat status, bukan waktu,
 * jadi order basi harus di-expire eksplisit agar tidak memblokir
 * pembelian berikutnya selamanya. Return jumlah order yang ditutup.
 */
export async function expireStaleBillingOrders(
  guildId: string,
  planId: string,
): Promise<number> {
  const { rows } = await sql`
    UPDATE billing_orders
    SET status = 'expired', updated_at = NOW()
    WHERE guild_id = ${guildId} AND plan_id = ${planId}
      AND status IN ('created', 'pending') AND expires_at <= NOW()
    RETURNING id
  `;
  return rows.length;
}

/**
 * Perbarui updated_at order non-terminal TANPA mengubah status — dipakai
 * jalur rekonsiliasi malas (GET detail order) untuk mencatat PERCOBAAN
 * rekonsiliasi, agar throttle 30 detik di route benar-benar menahan
 * panggilan fetchStatus berulang walau status provider tidak berubah
 * (transisi pending->pending tidak menyentuh baris mana pun).
 */
export async function touchBillingOrderReconcile(orderRef: string): Promise<void> {
  await sql`
    UPDATE billing_orders
    SET updated_at = NOW()
    WHERE order_ref = ${orderRef} AND status IN ('created', 'pending')
  `;
}

export type ApplyPaymentResult =
  | "activated"
  | "extended"
  | "noop_permanent"
  | "blocked_suspended";

/** Audit saja: pembayaran masuk saat guild suspended — entitlement TIDAK diubah. */
async function applyPaymentToEntitlementSuspendedAudit(
  row: GuildEntitlement,
  actor: string,
  reason: string,
): Promise<ApplyPaymentResult> {
  await sql`
    INSERT INTO entitlement_audit_log
      (guild_id, actor_id, action, tier_before, tier_after, status_before, status_after, expires_before, expires_after, reason)
    VALUES (${row.guild_id}, ${actor}, ${"payment_blocked_suspended"},
      ${row.tier}, ${row.tier},
      ${row.status}, ${row.status},
      ${row.expires_at}, ${row.expires_at}, ${reason})
  `;
  return "blocked_suspended";
}

/** Audit saja: pembayaran masuk saat VIP permanen aktif — entitlement TIDAK diubah. */
async function applyPaymentToEntitlementPermanentAudit(
  row: GuildEntitlement,
  actor: string,
  reason: string,
): Promise<ApplyPaymentResult> {
  await sql`
    INSERT INTO entitlement_audit_log
      (guild_id, actor_id, action, tier_before, tier_after, status_before, status_after, expires_before, expires_after, reason)
    VALUES (${row.guild_id}, ${actor}, ${"payment_noop_permanent"},
      ${row.tier}, ${row.tier},
      ${row.status}, ${row.status},
      ${row.expires_at}, ${row.expires_at}, ${reason})
  `;
  return "noop_permanent";
}

/**
 * Terapkan pembayaran yang sudah terverifikasi ke entitlement guild.
 *
 * Aturan (urutan penting):
 * - status 'suspended' -> TIDAK diubah; audit 'payment_blocked_suspended',
 *   return 'blocked_suspended'. Pembayaran tidak mengaktifkan guild yang
 *   sedang disuspend — perlu keputusan owner.
 * - VIP aktif permanen (expires_at NULL) -> TIDAK diubah; audit
 *   'payment_noop_permanent', return 'noop_permanent'. Pembayaran tidak
 *   pernah mengubah VIP permanen menjadi bertenggat.
 * - Selain itu VIP diaktifkan/diperpanjang: base perpanjangan adalah
 *   expires_at lama bila guild masih VIP aktif yang belum kedaluwarsa,
 *   selain itu sekarang; expires baru = base + durationDays hari.
 *   starts_at dipertahankan hanya bila sebelumnya VIP aktif itu, selain
 *   itu starts_at = sekarang. source menjadi 'payment',
 *   granted_by = 'system:' + provider. Audit mengikuti pola
 *   applyEntitlementMutation (action 'extend' bila sebelumnya VIP aktif,
 *   selain itu 'grant'; tier/status/expires before-after; reason memuat
 *   'payment', provider, order_ref, dan note bila ada).
 *
 * Baris entitlement dibaca lewat getEntitlement dan dibuat lewat
 * ensureEntitlement bila belum ada. Penulisan entitlement dan audit
 * adalah dua statement berurutan (tidak atomik penuh, keterbatasan yang
 * sama seperti applyEntitlementMutation). Melempar Error bila database
 * tidak terkonfigurasi / baris entitlement tidak bisa dibuat, agar
 * pemanggil tidak mengira pembayaran berhasil diterapkan.
 */
export async function applyPaymentToEntitlement(
  guildId: string,
  durationDays: number,
  provider: string,
  orderRef: string,
  note?: string | null,
): Promise<ApplyPaymentResult> {
  const actor = `system:${provider}`;
  const reason = (
    `payment via ${provider} order_ref=${orderRef}` + (note ? ` note=${note}` : "")
  ).slice(0, 500);

  let before = await getEntitlement(guildId);
  if (!before) before = await ensureEntitlement(guildId);
  if (!before) {
    throw new Error(
      "applyPaymentToEntitlement: entitlement guild tidak ditemukan dan database tidak terkonfigurasi",
    );
  }

  if (before.status === "suspended") {
    return applyPaymentToEntitlementSuspendedAudit(before, actor, reason);
  }

  if (before.tier === "vip" && before.status === "active" && before.expires_at === null) {
    return applyPaymentToEntitlementPermanentAudit(before, actor, reason);
  }

  const now = new Date();
  const isActiveVip =
    before.tier === "vip" &&
    before.status === "active" &&
    before.expires_at !== null &&
    new Date(before.expires_at).getTime() > now.getTime();

  // Perpanjangan dihitung DI DALAM SQL dari nilai baris yang terkunci
  // saat UPDATE berjalan (bukan dari snapshot bacaan TS di atas): dua
  // pembayaran berbeda untuk guild yang sama yang diproses bersamaan
  // terserialisasi oleh kunci baris, dan CASE mengevaluasi expires_at
  // versi terbaru — tidak ada lost update (dibayar 60 hari, diterima 30).
  // provider_entitlement_id mencatat order pendana periode berjalan:
  // dipakai service untuk memulihkan klaim yang penerapannya terputus
  // dan oleh refund untuk memastikan atribusi. Syarat penjaga
  // (bukan suspended, bukan VIP permanen) diulang di WHERE agar state
  // yang berubah bersamaan tidak lolos.
  const { rows } = await sql`
    UPDATE guild_entitlements
    SET tier = 'vip',
        status = 'active',
        source = 'payment',
        starts_at = CASE
          WHEN (tier = 'vip' AND status = 'active' AND expires_at IS NOT NULL AND expires_at > NOW())
          THEN starts_at ELSE NOW() END,
        expires_at = CASE
          WHEN (tier = 'vip' AND status = 'active' AND expires_at IS NOT NULL AND expires_at > NOW())
          THEN expires_at + make_interval(days => ${durationDays})
          ELSE NOW() + make_interval(days => ${durationDays}) END,
        provider_entitlement_id = ${orderRef},
        granted_by = ${actor},
        updated_at = NOW()
    WHERE guild_id = ${guildId}
      AND status <> 'suspended'
      AND NOT (tier = 'vip' AND status = 'active' AND expires_at IS NULL)
    RETURNING *
  `;
  if (rows.length === 0) {
    // State berubah di antara bacaan awal dan UPDATE (balapan dengan
    // operasi owner): evaluasi ulang sekali dari baris terbaru.
    const fresh = await getEntitlement(guildId);
    if (fresh && fresh.status === "suspended") {
      return applyPaymentToEntitlementSuspendedAudit(fresh, actor, reason);
    }
    if (
      fresh &&
      fresh.tier === "vip" &&
      fresh.status === "active" &&
      fresh.expires_at === null
    ) {
      return applyPaymentToEntitlementPermanentAudit(fresh, actor, reason);
    }
    throw new Error(
      "applyPaymentToEntitlement: UPDATE entitlement tidak menghasilkan baris",
    );
  }
  const after = mapEntitlementRow(rows[0] as Record<string, unknown>);
  await sql`
    INSERT INTO entitlement_audit_log
      (guild_id, actor_id, action, tier_before, tier_after, status_before, status_after, expires_before, expires_after, reason)
    VALUES (${guildId}, ${actor}, ${isActiveVip ? "extend" : "grant"},
      ${before.tier}, 'vip',
      ${before.status}, 'active',
      ${before.expires_at}, ${after.expires_at}, ${reason})
  `;
  return isActiveVip ? "extended" : "activated";
}

/**
 * Kurangi / cabut entitlement akibat refund pembayaran yang
 * terverifikasi, SEBESAR durasi order yang direfund — bukan seluruh
 * masa aktif. Hanya menyentuh baris yang SAAT INI source-nya 'payment'
 * DAN status-nya 'active' (kondisi diulang di WHERE UPDATE sebagai
 * penjaga race):
 * - expires_at ada: expires_at dikurangi durationDays hari di dalam
 *   SQL; bila sisa masa habis (<= sekarang) status menjadi 'revoked',
 *   selain itu entitlement tetap 'active' dengan masa yang lebih
 *   pendek (masa dari order LAIN yang tidak direfund tetap utuh).
 * - expires_at NULL (permanen dari payment — tidak terjadi lewat alur
 *   apply saat ini, tetapi dijaga): dicabut penuh.
 * Audit action 'refund' ditulis dengan expires/status before-after dari
 * baris hasil UPDATE. Entitlement hasil grant owner (source
 * 'owner_grant') TIDAK pernah tersentuh refund — return false tanpa
 * perubahan apa pun, sama seperti baris yang tidak aktif / tidak ada.
 * Return true hanya bila pengurangan/pencabutan benar-benar terjadi.
 */
export async function revokeEntitlementForRefund(
  guildId: string,
  provider: string,
  orderRef: string,
  durationDays: number,
): Promise<boolean> {
  if (!dbConfigured()) return false;
  const before = await getEntitlement(guildId);
  if (!before || before.source !== "payment" || before.status !== "active") {
    return false;
  }
  const { rows } =
    before.expires_at === null
      ? await sql`
          UPDATE guild_entitlements
          SET status = 'revoked', updated_at = NOW()
          WHERE guild_id = ${guildId} AND source = 'payment' AND status = 'active'
          RETURNING *
        `
      : await sql`
          UPDATE guild_entitlements
          SET expires_at = expires_at - make_interval(days => ${durationDays}),
              status = CASE
                WHEN expires_at - make_interval(days => ${durationDays}) <= NOW()
                THEN 'revoked' ELSE 'active' END,
              updated_at = NOW()
          WHERE guild_id = ${guildId} AND source = 'payment' AND status = 'active'
            AND expires_at IS NOT NULL
          RETURNING *
        `;
  if (rows.length === 0) return false;
  const after = mapEntitlementRow(rows[0] as Record<string, unknown>);
  const reason = (
    `payment refund via ${provider} order_ref=${orderRef} durasi_dikurangi=${durationDays} hari`
  ).slice(0, 500);
  await sql`
    INSERT INTO entitlement_audit_log
      (guild_id, actor_id, action, tier_before, tier_after, status_before, status_after, expires_before, expires_after, reason)
    VALUES (${guildId}, ${`system:${provider}`}, ${"refund"},
      ${before.tier}, ${after.tier},
      ${before.status}, ${after.status},
      ${before.expires_at}, ${after.expires_at}, ${reason})
  `;
  return true;
}
