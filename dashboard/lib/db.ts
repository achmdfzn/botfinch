import { sql } from "@vercel/postgres";

export function dbConfigured(): boolean {
  return Boolean(process.env.POSTGRES_URL);
}

export async function latestSnapshot(): Promise<SnapshotPayload | null> {
  if (!dbConfigured()) return null;
  const { rows } = await sql`SELECT payload FROM snapshots ORDER BY id DESC LIMIT 1`;
  return (rows[0]?.payload as SnapshotPayload) ?? null;
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
  const { rows } = await sql`SELECT * FROM selfroles WHERE guild_id = ${guildId} ORDER BY id`;
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

export async function getPendingGiveawayRequests(): Promise<GiveawayRequest[]> {
  if (!dbConfigured()) return [];
  const { rows } = await sql`SELECT * FROM giveaway_requests WHERE status = 'pending' ORDER BY id LIMIT 25`;
  return rows as GiveawayRequest[];
}

export async function ackGiveawayRequest(id: number, status: "done" | "failed", note: string): Promise<void> {
  await sql`UPDATE giveaway_requests SET status = ${status}, note = ${note} WHERE id = ${id}`;
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

export async function updateAnnouncement(
  id: number,
  guildId: string,
  patch: AnnouncementPatch,
): Promise<void> {
  if (patch.message !== undefined) {
    await sql`UPDATE announcements SET message = ${patch.message} WHERE id = ${id} AND guild_id = ${guildId}`;
  }
  if (patch.channelId !== undefined) {
    await sql`UPDATE announcements SET channel_id = ${patch.channelId} WHERE id = ${id} AND guild_id = ${guildId}`;
  }
  if (patch.runAt !== undefined) {
    await sql`UPDATE announcements SET run_at = ${patch.runAt} WHERE id = ${id} AND guild_id = ${guildId}`;
  }
  if (patch.intervalMinutes !== undefined) {
    await sql`UPDATE announcements SET interval_minutes = ${patch.intervalMinutes} WHERE id = ${id} AND guild_id = ${guildId}`;
  }
  if (patch.enabled !== undefined) {
    await sql`UPDATE announcements SET enabled = ${patch.enabled} WHERE id = ${id} AND guild_id = ${guildId}`;
  }
}

export async function deleteAnnouncement(id: number, guildId: string): Promise<void> {
  await sql`DELETE FROM announcements WHERE id = ${id} AND guild_id = ${guildId}`;
}
