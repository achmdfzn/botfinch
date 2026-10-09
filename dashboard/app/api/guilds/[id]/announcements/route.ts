import { NextResponse } from "next/server";
import { createAnnouncement, listAnnouncements } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, intervalMinutes, isoDateTime, str } from "@/lib/validate";

export const instant = false;

/** Daftar pengumuman terjadwal/berulang (manager). */
export async function GET(
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
export async function POST(
  req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
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
