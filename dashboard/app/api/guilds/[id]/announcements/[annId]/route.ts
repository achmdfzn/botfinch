import { NextResponse } from "next/server";
import {
  deleteAnnouncement,
  updateAnnouncement,
  type AnnouncementPatch,
} from "@/lib/db";
import { requireManager } from "@/lib/access";
import { discordId, intervalMinutes, isoDateTime, str } from "@/lib/validate";

export const instant = false;

function invalidId(reqId: string): boolean {
  const n = Number(reqId);
  return !Number.isInteger(n) || n <= 0;
}

/** Ubah sebagian field pengumuman (manager). */
export async function PUT(
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
  let body: Record<string, unknown>;
  try {
    body = (await req.json()) as Record<string, unknown>;
  } catch {
    return NextResponse.json({ error: "invalid_json" }, { status: 400 });
  }
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
export async function DELETE(
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
