import { NextResponse } from "next/server";
import {
  dbConfigured,
  ensureEntitlement,
  getAutoResponses,
  getEntitlement,
  getSelfRoles,
  getStoredSettings,
  listAnnouncements,
  type GiveawayRequest, withDbError } from "@/lib/db";
import { sql } from "@vercel/postgres";
import { botAuthorized } from "@/lib/access";


/**
 * Satu endpoint tarik untuk bot: pengaturan + self-roles + auto-responder
 * + permintaan giveaway yang pending, untuk satu guild.
 */
async function getImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  const stored = await getStoredSettings(id);
  const { rows } = await sql`SELECT * FROM giveaway_requests WHERE guild_id = ${id} AND status = 'pending' ORDER BY id LIMIT 10`;
  const { rows: pendingEmbeds } =
    await sql`SELECT id, guild_id, channel_id, title, description, color, fields, footer, image_url, thumbnail_url
      FROM embed_requests WHERE guild_id = ${id} AND status = 'pending' ORDER BY id LIMIT 10`;
  // Announcement: hanya field yang dibutuhkan bot (run_at/last_sent_at sudah ISO via listAnnouncements).
  const announcements = (await listAnnouncements(id)).map((a) => ({
    id: a.id,
    guild_id: a.guild_id,
    channel_id: a.channel_id,
    message: a.message,
    run_at: a.run_at,
    interval_minutes: a.interval_minutes,
    enabled: a.enabled,
    last_sent_at: a.last_sent_at,
  }));
  // Entitlement tier guild: guild yang belum punya baris didaftarkan malas
  // (lazy) sebagai free lewat ensureEntitlement. Bila baris tetap null
  // (kegagalan parsial DB), kirim default free agar bot tetap jalan.
  let entitlementRow = await getEntitlement(id);
  if (!entitlementRow) entitlementRow = await ensureEntitlement(id);
  const entitlement = entitlementRow
    ? {
        tier: entitlementRow.tier,
        status: entitlementRow.status,
        starts_at: entitlementRow.starts_at,
        expires_at: entitlementRow.expires_at,
        source: entitlementRow.source,
        updated_at: entitlementRow.updated_at,
      }
    : {
        tier: "free",
        status: "active",
        starts_at: null,
        expires_at: null,
        source: "default",
        updated_at: null,
      };
  // NOTE: kirim mentah (tanpa merge default) — default ditentukan di code bot
  // via get_guild_setting(key, default), agar key yang belum disimpan user
  // tidak menimpa perilaku lama.
  return NextResponse.json({
    ok: true,
    guild_id: id,
    settings: stored,
    selfroles: await getSelfRoles(id),
    autoresponses: await getAutoResponses(id),
    giveaway_requests: rows as GiveawayRequest[],
    embed_requests: pendingEmbeds,
    announcements,
    entitlement,
  });
}

export const GET = withDbError(getImpl);
