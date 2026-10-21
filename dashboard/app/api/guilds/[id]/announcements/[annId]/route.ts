import { NextResponse } from "next/server";
import {
  dbConfigured,
  deleteAnnouncement,
  getSnapshotChannel,
  markAnnouncementSent,
  updateAnnouncement,
  type AnnouncementPatch,
  withDbError,
} from "@/lib/db";
import { botAuthorized, requireManager } from "@/lib/access";
import { discordId, intervalMinutes, isoDateTime, parseJsonBody, str } from "@/lib/validate";


function invalidId(reqId: string): boolean {
  const n = Number(reqId);
  return !Number.isInteger(n) || n <= 0;
}

/** Ubah sebagian field pengumuman (manager). */
async function putImpl(
  req: Request,
  { params }: { params: Promise<{ id: string; annId: string }> },
) {
  const { id, annId } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  const aid = Number(annId);
  if (invalidId(annId)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const patch: AnnouncementPatch = {};
  if ("enabled" in body) {
    if (typeof body.enabled !== "boolean") {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    patch.enabled = body.enabled;
  }
  if ("message" in body) {
    const message = str(body.message, 2000, true);
    if (message === undefined) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    patch.message = message;
  }
  if ("channel_id" in body) {
    const channelId = discordId(body.channel_id);
    if (channelId === undefined) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    const target = await getSnapshotChannel(id, channelId);
    if (!target || (target.type !== 0 && target.type !== 5)) {
      return NextResponse.json({ error: "channel_not_in_guild_or_not_text" }, { status: 400 });
    }
    patch.channelId = channelId;
  }
  if ("run_at" in body) {
    const runAt = isoDateTime(body.run_at);
    if (runAt === undefined) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    patch.runAt = runAt;
  }
  if ("interval_minutes" in body) {
    const interval = intervalMinutes(body.interval_minutes);
    if (interval === undefined) {
      return NextResponse.json({ error: "invalid_input" }, { status: 400 });
    }
    patch.intervalMinutes = interval;
  }
  if (Object.keys(patch).length === 0) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await updateAnnouncement(aid, id, patch);
  return NextResponse.json({ ok: true });
}

/** Hapus pengumuman (manager). */
async function deleteImpl(
  _req: Request,
  { params }: { params: Promise<{ id: string; annId: string }> },
) {
  const { id, annId } = await params;
  const denied = await requireManager(id);
  if (denied) return denied;
  if (invalidId(annId)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  await deleteAnnouncement(Number(annId), id);
  return NextResponse.json({ ok: true });
}

/** Bot menandai jadwal terkirim menggunakan shared DASHBOARD_SECRET. */
async function postAckImpl(
  req: Request,
  { params }: { params: Promise<{ id: string; annId: string }> },
) {
  const { id, annId } = await params;
  if (!botAuthorized(req)) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }
  if (!dbConfigured()) {
    return NextResponse.json({ error: "database_not_configured" }, { status: 503 });
  }
  if (invalidId(annId)) {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const body = await parseJsonBody(req);
  if (!body) return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  const lastSentAt = isoDateTime(body.last_sent_at);
  if (typeof lastSentAt !== "string") {
    return NextResponse.json({ error: "invalid_input" }, { status: 400 });
  }
  const updated = await markAnnouncementSent(Number(annId), id, lastSentAt);
  if (!updated) return NextResponse.json({ error: "announcement_not_found" }, { status: 404 });
  return NextResponse.json({ ok: true });
}

export const PUT = withDbError(putImpl);
export const DELETE = withDbError(deleteImpl);
export const POST = withDbError(postAckImpl);
