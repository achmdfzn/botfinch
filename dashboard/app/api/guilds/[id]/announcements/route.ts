import { NextResponse } from "next/server";
import { createAnnouncement, listAnnouncements, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, intervalMinutes, isoDateTime, parseJsonBody, str } from "@/lib/validate";


/** Daftar pengumuman terjadwal/berulang (manager). */
async function getImpl(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  return NextResponse.json({
    ok: true,
    guild_id: id,
    announcements: await listAnnouncements(id),
  });
}

/** Buat pengumuman baru (dieksekusi bot). */
async function postImpl(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const channelId = discordId(body.channel_id);
  const message = str(body.message, 2000, true);
  const runAt = isoDateTime(body.run_at);
  const interval = intervalMinutes(body.interval_minutes);
  if (
    channelId === undefined ||
    message === undefined ||
    runAt === undefined ||
    interval === undefined
  ) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const annId = await createAnnouncement({
    guildId: id,
    channelId,
    message,
    runAt,
    intervalMinutes: interval,
  });
  return NextResponse.json({ ok: true, id: annId });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
