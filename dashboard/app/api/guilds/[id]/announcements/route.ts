import { NextResponse } from "next/server";
import { createAnnouncementWithQuota, getEntitlement, getSnapshotChannel, listAnnouncements, withDbError } from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, intervalMinutes, isoDateTime, parseJsonBody, str } from "@/lib/validate";
import { FEATURE_LIMITS, getEffectiveTierFromRow } from "@/lib/premium";


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
  const target = await getSnapshotChannel(id, channelId);
  if (!target || (target.type !== 0 && target.type !== 5)) {
    return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
  }
  // Kuota pengumuman aktif per tier efektif guild. Pembuatan memakai
  // createAnnouncementWithQuota (satu statement atomik) agar balapan
  // antar request tidak bisa menembus batas.
  const tier = getEffectiveTierFromRow(await getEntitlement(id));
  const limit = FEATURE_LIMITS.announcements_active[tier];
  const annId = await createAnnouncementWithQuota(
    {
      guildId: id,
      channelId,
      message,
      runAt,
      intervalMinutes: interval,
    },
    limit,
  );
  if (annId === null) {
    return NextResponse.json(
      { error: "announcement_quota_exceeded", limit },
      { status: 409 },
    );
  }
  return NextResponse.json({ ok: true, id: annId });
}

export const GET = withDbError(getImpl);
export const POST = withDbError(postImpl);
